import base64

from ..base import ImageBlock, VisionRequest
from .http import HTTPProvider


class OllamaProvider(HTTPProvider):
    def encode(self, request: VisionRequest) -> tuple[str, dict, dict]:
        messages = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})
        text = [request.user_text]
        images = []
        for block in request.blocks:
            if isinstance(block, ImageBlock):
                text.append(f"Image {len(images) + 1}: frame at {block.timestamp:.3f}s")
                images.append(base64.b64encode(block.data).decode())
            else:
                text.append(block.text)
        user = {"role": "user", "content": "\n".join(text)}
        if images:
            user["images"] = images
        messages.append(user)
        options = {"num_predict": request.max_tokens}
        if request.temperature is not None:
            options["temperature"] = request.temperature
        payload = {"model": self.config.model, "messages": messages, "stream": False, "options": options}
        if request.response_format:
            payload["format"] = "json"
        headers = {"Authorization": f"Bearer {self.config.api_key}"} if self.config.api_key else {}
        return "/api/chat", headers, payload

    def decode(self, data: dict) -> tuple[str, dict | None, bool]:
        usage = {k: data[k] for k in ("prompt_eval_count", "eval_count") if k in data}
        return data["message"]["content"], usage, not data.get("done") or data.get("done_reason") == "length"
