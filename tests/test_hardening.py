import io
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

import httpx
import pytest
from PIL import Image

from test_http import image_block
from vidsight.media.frames import prepare_request
from vidsight.providers.base import (Capabilities, ImageBlock, ProviderTimeoutError,
                                    TextBlock, UnsupportedCapabilityError, VisionRequest)
from vidsight.providers.config import ProviderConfig
from vidsight.providers.registry import create_provider


def test_media_budget_and_formats():
    caps = Capabilities(supports_images=True, context_tokens=6000, image_formats=("png",))
    req = VisionRequest(None, "question", tuple(TextBlock(f"[{i}s] " + "a" * 3000) for i in range(10)) +
                        tuple(image_block(i) for i in range(12)))
    prepared, warnings = prepare_request(req, caps)
    assert len(warnings) >= 2
    images = [b for b in prepared.blocks if isinstance(b, ImageBlock)]
    assert images and images[0].mime_type == "image/png"
    with Image.open(io.BytesIO(images[0].data)) as image:
        assert image.format == "PNG"
    assert "[0s]" in prepared.blocks[0].text
    assert "[9s]" in [b for b in prepared.blocks if isinstance(b, TextBlock)][-1].text


@pytest.mark.parametrize("block", [ImageBlock(b"broken", "image/jpeg", 0), image_block(-1), image_block(float("nan"))])
def test_bad_images(block):
    with pytest.raises(UnsupportedCapabilityError):
        prepare_request(VisionRequest(None, "q", (block,)), Capabilities(supports_images=True))


def test_timeout_retry_and_safe_error():
    requests, sleeps = [], []
    def handler(req):
        requests.append(req)
        raise httpx.ReadTimeout("secret request body", request=req)
    provider = create_provider(ProviderConfig("openai", "m", "https://test/v1"),
                               transport=httpx.MockTransport(handler), sleep=sleeps.append)
    try:
        with pytest.raises(ProviderTimeoutError) as caught:
            provider.generate(VisionRequest(None, "private transcript"))
        assert len(requests) == 4 and len(sleeps) == 3
        assert "secret" not in str(caught.value) and caught.value.__cause__ is None
    finally:
        provider.close()


def test_retry_after_date():
    calls, sleeps = [], []
    def handler(req):
        calls.append(req)
        if len(calls) == 1:
            return httpx.Response(429, headers={"Retry-After": format_datetime(datetime.now(timezone.utc) + timedelta(seconds=2))})
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]})
    provider = create_provider(ProviderConfig("openai", "m", "https://test/v1"),
                               transport=httpx.MockTransport(handler), sleep=sleeps.append)
    try:
        assert provider.generate(VisionRequest(None, "q")).text == "ok"
        assert len(calls) == 2 and 0 <= sleeps[0] <= 2
    finally:
        provider.close()


def test_small_frame_does_not_upscale():
    req, warnings = prepare_request(VisionRequest(None, "q", (image_block(),)), Capabilities(supports_images=True))
    with Image.open(io.BytesIO(req.blocks[0].data)) as image:
        assert image.size == (40, 20)
    assert not warnings
    assert prepare_request(replace(req, blocks=()), Capabilities())[0].blocks == ()


def test_sampling_uses_elapsed_time():
    blocks = tuple(image_block(t) for t in (0, 1, 2, 3, 50, 100))
    prepared, _ = prepare_request(VisionRequest(None, "q", blocks),
                                  Capabilities(supports_images=True, max_images_per_request=3))
    assert [b.timestamp for b in prepared.blocks] == [0, 50, 100]
