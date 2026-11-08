"""Synchronous, vendor independent contracts; no raw provider payloads in results."""
from dataclasses import dataclass, field
from typing import Literal, Protocol


class ProviderError(Exception):
    """Safe public error, without request/response bodies."""


class ConfigurationError(ProviderError):
    pass


class UnsupportedCapabilityError(ProviderError):
    pass


class AuthenticationError(ProviderError):
    pass


class RateLimitError(ProviderError):
    pass


class ProviderTimeoutError(ProviderError):
    pass


class ProviderResponseError(ProviderError):
    pass


@dataclass(frozen=True)
class Capabilities:
    supports_images: bool = False
    image_formats: tuple[str, ...] = ("jpeg",)
    max_images_per_request: int = 12
    max_image_side_px: int = 1024
    supports_native_video: bool = False
    supports_system_prompt: bool = True
    supports_json_mode: bool = False
    context_tokens: int = 8192


@dataclass(frozen=True)
class TextBlock:
    text: str
    type: Literal["text"] = field(default="text", init=False)


@dataclass(frozen=True)
class ImageBlock:
    data: bytes = field(repr=False)
    mime_type: Literal["image/jpeg", "image/png", "image/webp"]
    timestamp: float
    type: Literal["image"] = field(default="image", init=False)


ContentBlock = TextBlock | ImageBlock


@dataclass(frozen=True)
class VisionRequest:
    system_prompt: str | None
    user_text: str
    blocks: tuple[ContentBlock, ...] = ()
    temperature: float | None = None
    max_tokens: int = 1024
    response_format: str | None = None


@dataclass(frozen=True)
class VisionResponse:
    text: str
    provider: str
    model: str
    usage: dict[str, int] | None = None
    warnings: tuple[str, ...] = ()
    truncated: bool = False
    valid_json: bool | None = None


class VisionProvider(Protocol):
    def generate(self, request: VisionRequest) -> VisionResponse: ...
    def close(self) -> None: ...
