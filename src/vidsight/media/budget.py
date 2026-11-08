"""Conservative estimates, explicit reduction warnings, no extra model calls."""
from dataclasses import replace

from ..providers.base import (Capabilities, ImageBlock, TextBlock,
                              UnsupportedCapabilityError, VisionRequest)


def even_sample(items: list, count: int) -> list:
    if count >= len(items):
        return items
    if count == 1:
        return items[:1]
    return [items[round(i * (len(items) - 1) / (count - 1))] for i in range(count)]


def temporal_sample(images: list[ImageBlock], count: int) -> list[ImageBlock]:
    images = sorted(images, key=lambda b: b.timestamp)
    if count >= len(images) or count == 1:
        return images if count >= len(images) else images[:1]
    selected = {0, len(images) - 1}
    for i in range(1, count - 1):
        target = images[0].timestamp + i * (images[-1].timestamp - images[0].timestamp) / (count - 1)
        candidates = (j for j in range(len(images)) if j not in selected)
        selected.add(min(candidates, key=lambda j: abs(images[j].timestamp - target)))
    return [images[j] for j in sorted(selected)]


def fit_budget(request: VisionRequest, caps: Capabilities) -> tuple[VisionRequest, tuple[str, ...]]:
    # One token per UTF-8 byte for text is deliberately conservative.
    # 1536/image is an approximation, not a vendor accounting rule.
    available = caps.context_tokens - request.max_tokens - 256 - len(
        ((request.system_prompt or "") + request.user_text).encode())
    texts = [b for b in request.blocks if isinstance(b, TextBlock)]
    images = [b for b in request.blocks if isinstance(b, ImageBlock)]
    minimum = (1536 if images else 0) + (128 if texts else 0)
    if available < minimum or available < 0:
        raise UnsupportedCapabilityError("Prompt/output reserve exceeds context budget; narrow question or raise verified LLM_CONTEXT_TOKENS")
    warnings = []
    image_budget = available // 2 if texts and images else available
    kept_images = temporal_sample(images, min(len(images), max(1, image_budget // 1536))) if images else []
    if len(kept_images) < len(images):
        warnings.append(f"Context budget: sampled {len(kept_images)}/{len(images)} frames across time.")
    text_budget = available - len(kept_images) * 1536
    kept_texts = texts
    original_size = sum(len(b.text.encode()) for b in texts)
    if original_size > text_budget:
        count = max(1, min(len(texts), text_budget // 128))
        kept_texts = even_sample(texts, count)
        per_block = text_budget // count
        marker = " …[omitted]… "
        def trim(block: TextBlock) -> TextBlock:
            data = block.text.encode()
            if len(data) <= per_block:
                return block
            size = max(0, (per_block - len(marker.encode())) // 2)
            return TextBlock(data[:size].decode("utf-8", errors="ignore") + marker +
                             data[-size:].decode("utf-8", errors="ignore") if size else marker)
        kept_texts = [trim(b) for b in kept_texts]
        warnings.append(f"Context budget: reduced transcript/text from {len(texts)} blocks/{original_size} bytes to {len(kept_texts)} sampled blocks; evidence incomplete.")
    # Keep original block order while replacing trimmed text.
    selected_texts = even_sample(texts, len(kept_texts)) if texts else []
    replacements = {id(old): new for old, new in zip(selected_texts, kept_texts)}
    selected_images = {id(b) for b in kept_images}
    blocks = tuple(replacements[id(b)] if isinstance(b, TextBlock) else b for b in request.blocks
                   if id(b) in replacements or id(b) in selected_images)
    return replace(request, blocks=blocks), tuple(warnings)
