import base64

from ..base import ImageBlock, VisionRequest
from .http import HTTPProvider


def messages(request: VisionRequest) -> list[dict]:
    content = [{"type": "text", "text": request.user_text}]
    for block in request.blocks:
        if isinstance(block, ImageBlock):
            content.extend([
                {"type": "text", "text": f"Frame at {block.timestamp:.3f}s"},
                {"type": "image_url", "image_url": {"url":
                    f"data:{block.mime_type};base64,{base64.b64encode(block.data).decode()}"}},
            ])
        else:
            content.append({"type": "text", "text": block.text})
    result = []
    if request.system_prompt:
        result.append({"role": "system", "content": request.system_prompt})
    return [*result, {"role": "user", "content": content}]


class OpenAIChatProvider(HTTPProvider):
    def encode(self, request: VisionRequest) -> tuple[str, dict, dict]:
        payload = {"model": self.config.model, "messages": messages(request),
                   "max_tokens": request.max_tokens, "stream": False}
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.response_format:
            payload["response_format"] = {"type": request.response_format}
        headers = {"Authorization": f"Bearer {self.config.api_key}"} if self.config.api_key else {}
        return "/chat/completions", headers, payload

    def decode(self, data: dict) -> tuple[str, dict | None, bool]:
        choice = data["choices"][0]
        return choice["message"]["content"], data.get("usage"), choice.get("finish_reason") != "stop"
