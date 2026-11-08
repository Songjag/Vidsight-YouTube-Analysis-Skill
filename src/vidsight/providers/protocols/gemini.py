import base64
from urllib.parse import quote

from ..base import ImageBlock, VisionRequest
from .http import HTTPProvider


class GeminiProvider(HTTPProvider):
    def encode(self, request: VisionRequest) -> tuple[str, dict, dict]:
        parts = [{"text": request.user_text}]
        for block in request.blocks:
            if isinstance(block, ImageBlock):
                parts.extend([{"text": f"Frame at {block.timestamp:.3f}s"},
                              {"inlineData": {"mimeType": block.mime_type,
                                              "data": base64.b64encode(block.data).decode()}}])
            else:
                parts.append({"text": block.text})
        options = {"maxOutputTokens": request.max_tokens}
        if request.temperature is not None:
            options["temperature"] = request.temperature
        if request.response_format:
            options["responseMimeType"] = "application/json"
        payload = {"contents": [{"role": "user", "parts": parts}], "generationConfig": options}
        if request.system_prompt:
            payload["systemInstruction"] = {"parts": [{"text": request.system_prompt}]}
        model = quote(self.config.model.removeprefix("models/"), safe="")
        return f"/models/{model}:generateContent", {"x-goog-api-key": self.config.api_key}, payload

    def decode(self, data: dict) -> tuple[str, dict | None, bool]:
        candidate = data["candidates"][0]
        text = "".join(p["text"] for p in candidate["content"]["parts"]
                       if "text" in p and not p.get("thought"))
        return text, data.get("usageMetadata"), candidate.get("finishReason") != "STOP"
