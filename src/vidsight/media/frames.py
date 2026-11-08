import io
import math
from dataclasses import replace

from PIL import Image, UnidentifiedImageError

from ..providers.base import (Capabilities, ImageBlock,
                              UnsupportedCapabilityError, VisionRequest)
from .budget import fit_budget, temporal_sample


def sample_indices(count: int, limit: int) -> list[int]:
    if count <= limit:
        return list(range(count))
    if limit == 1:
        return [0]
    return [round(i * (count - 1) / (limit - 1)) for i in range(limit)]


def normalize_image(block: ImageBlock, caps: Capabilities) -> ImageBlock:
    if not math.isfinite(block.timestamp) or block.timestamp < 0:
        raise UnsupportedCapabilityError("Image timestamp must be finite and nonnegative")
    if len(block.data) > 12 * 1024 * 1024:
        raise UnsupportedCapabilityError("Encoded image exceeds Vidsight 12 MiB limit")
    try:
        with Image.open(io.BytesIO(block.data)) as image:
            image.load()
            image.thumbnail((caps.max_image_side_px, caps.max_image_side_px))
            fmt = caps.image_formats[0]
            output = io.BytesIO()
            image.convert("RGB").save(output, format=fmt.upper())
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise UnsupportedCapabilityError("Invalid or oversized image") from None
    return ImageBlock(output.getvalue(), f"image/{fmt}", block.timestamp)


def prepare_request(request: VisionRequest, caps: Capabilities) -> tuple[VisionRequest, tuple[str, ...]]:
    if request.response_format and (request.response_format != "json_object" or not caps.supports_json_mode):
        raise UnsupportedCapabilityError("JSON mode is not enabled for this model")
    if request.max_tokens <= 0:
        raise UnsupportedCapabilityError("max_tokens must be positive")
    if not math.isfinite(request.max_tokens) or int(request.max_tokens) != request.max_tokens:
        raise UnsupportedCapabilityError("max_tokens must be an integer")
    if request.temperature is not None and not math.isfinite(request.temperature):
        raise UnsupportedCapabilityError("temperature must be finite")
    images = sorted((b for b in request.blocks if isinstance(b, ImageBlock)), key=lambda b: b.timestamp)
    if images and not caps.supports_images:
        raise UnsupportedCapabilityError("Model vision capability unknown/disabled; set LLM_SUPPORTS_IMAGES=true only after verification")
    warnings = []
    selected = temporal_sample(images, caps.max_images_per_request)
    normalized = {id(block): normalize_image(block, caps) for block in selected}
    if len(selected) < len(images):
        warnings.append(f"Sampled {len(selected)}/{len(images)} frames across the supplied time range.")
    blocks = tuple(normalized[id(b)] if isinstance(b, ImageBlock) else b for b in request.blocks
                   if not isinstance(b, ImageBlock) or id(b) in normalized)
    result = replace(request, blocks=blocks)
    result, budget_warnings = fit_budget(result, caps)
    if sum(len(b.data) for b in blocks if isinstance(b, ImageBlock)) > 12 * 1024 * 1024:
        raise UnsupportedCapabilityError("Image payload exceeds Vidsight 12 MiB budget; narrow range")
    return result, (*warnings, *budget_warnings)
