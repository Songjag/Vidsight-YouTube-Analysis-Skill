import io
import json
from dataclasses import replace

import httpx
import pytest
from PIL import Image

from vidsight.providers.base import (AuthenticationError, Capabilities, ImageBlock,
                                    ProviderResponseError, VisionRequest)
from vidsight.providers.config import ProviderConfig
from vidsight.providers.registry import create_provider


def image_block(timestamp=0):
    out = io.BytesIO()
    Image.new("RGB", (40, 20)).save(out, "PNG")
    return ImageBlock(out.getvalue(), "image/png", timestamp)


def test_openai_contract():
    def handler(req):
        assert str(req.url) == "https://example.test/v1/chat/completions"
        assert req.headers["authorization"] == "Bearer private"
        body = json.loads(req.content)
        assert body["messages"][0] == {"role": "system", "content": "system"}
        assert body["messages"][1]["content"][2]["image_url"]["url"].startswith("data:image/jpeg;base64,")
        assert body["response_format"] == {"type": "json_object"}
        return httpx.Response(200, json={"choices": [{"message": {"content": "broken json"}, "finish_reason": "length"}],
                                         "usage": {"total_tokens": 10}})
    cfg = ProviderConfig("openai", "m", "https://example.test/v1", "private",
                         capabilities=Capabilities(supports_images=True, supports_json_mode=True))
    provider = create_provider(cfg, transport=httpx.MockTransport(handler))
    try:
        result = provider.generate(VisionRequest("system", "question", (image_block(),), response_format="json_object"))
        assert result.truncated and result.valid_json is False
        assert result.usage == {"total_tokens": 10}
    finally:
        provider.close()


@pytest.mark.parametrize("status,calls,error", [(401, 1, AuthenticationError), (403, 1, AuthenticationError),
                                               (429, 4, ProviderResponseError), (503, 4, ProviderResponseError),
                                               (302, 1, ProviderResponseError)])
def test_retry(status, calls, error):
    from vidsight.providers.base import RateLimitError
    requests, sleeps = [], []
    def handler(req):
        requests.append(req)
        return httpx.Response(status, headers={"Retry-After": "0", "Location": "https://other.test"}, text="private")
    provider = create_provider(ProviderConfig("openai", "m", "https://example.test/v1"),
                               transport=httpx.MockTransport(handler), sleep=sleeps.append)
    try:
        with pytest.raises(RateLimitError if status == 429 else error) as caught:
            provider.generate(VisionRequest(None, "hello"))
        assert "private" not in str(caught.value)
        assert len(requests) == calls
        assert len(sleeps) == calls - 1
    finally:
        provider.close()


def test_empty_response():
    provider = create_provider(ProviderConfig("openai", "m", "https://example.test/v1"),
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"choices": []})))
    with pytest.raises(ProviderResponseError):
        provider.generate(VisionRequest(None, "hello"))
    provider.close()


def test_media():
    from vidsight.media.frames import prepare_request
    from vidsight.providers.base import UnsupportedCapabilityError
    blocks = tuple(image_block(i) for i in range(5))
    req = VisionRequest(None, "question", blocks)
    with pytest.raises(UnsupportedCapabilityError):
        prepare_request(req, Capabilities())
    caps = Capabilities(supports_images=True, max_images_per_request=2, max_image_side_px=20)
    prepared, warnings = prepare_request(req, caps)
    assert [b.timestamp for b in prepared.blocks] == [0, 4]
    assert warnings
    with Image.open(io.BytesIO(prepared.blocks[0].data)) as image:
        assert image.size == (20, 10)
    assert len(prepare_request(req, replace(caps, max_images_per_request=1))[0].blocks) == 1
    with pytest.raises(UnsupportedCapabilityError):
        prepare_request(req, replace(caps, context_tokens=10))
