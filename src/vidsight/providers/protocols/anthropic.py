import base64

from ..base import ImageBlock, UnsupportedCapabilityError, VisionRequest
from .http import HTTPProvider


class AnthropicProvider(HTTPProvider):
    def encode(self, request: VisionRequest) -> tuple[str, dict, dict]:
        if request.response_format:
            raise UnsupportedCapabilityError("anthropic: JSON mode not implemented for Messages adapter")
        content = [{"type": "text", "text": request.user_text}]
        for block in request.blocks:
            if isinstance(block, ImageBlock):
                content.extend([
                    {"type": "text", "text": f"Frame at {block.timestamp:.3f}s"},
                    {"type": "image", "source": {"type": "base64", "media_type": block.mime_type,
                                                 "data": base64.b64encode(block.data).decode()}},
                ])
            else:
                content.append({"type": "text", "text": block.text})
        payload = {"model": self.config.model, "messages": [{"role": "user", "content": content}],
                   "max_tokens": request.max_tokens}
        if request.system_prompt:
            payload["system"] = request.system_prompt
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        return "/messages", {"x-api-key": self.config.api_key, "anthropic-version": "2023-06-01"}, payload

    def decode(self, data: dict) -> tuple[str, dict | None, bool]:
        text = "".join(b["text"] for b in data["content"] if b.get("type") == "text")
        return text, data.get("usage"), data.get("stop_reason") not in {"end_turn", "stop_sequence"}
