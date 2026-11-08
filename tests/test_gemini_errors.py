"""Gemini error tests never use real keys, quota or network."""
import httpx
import pytest

from vidsight.providers.base import (
    AuthenticationError, ProviderResponseError, ProviderTimeoutError,
    RateLimitError, VisionRequest,
)
from vidsight.providers.config import ProviderConfig
from vidsight.providers.registry import create_provider


@pytest.mark.parametrize("status,error,expected_calls", [
    (401, AuthenticationError, 1),
    (404, ProviderResponseError, 1),
    (429, RateLimitError, 3),
    (None, ProviderTimeoutError, 3),
])
def test_gemini_errors(status, error, expected_calls, caplog):
    calls, sleeps = [], []

    def handler(request):
        calls.append(request)
        assert request.url.path == "/v1beta/models/test-model:generateContent"
        assert request.headers["x-goog-api-key"] == "fake-private-key"
        if status is None:
            raise httpx.ReadTimeout("sensitive body", request=request)
        return httpx.Response(status, headers={"Retry-After": "0"},
                              json={"error": {"message": "sensitive body"}})

    config = ProviderConfig("gemini", "test-model", "https://generativelanguage.googleapis.com/v1beta",
                            "fake-private-key", max_retries=2)
    provider = create_provider(config, transport=httpx.MockTransport(handler), sleep=sleeps.append)
    try:
        with pytest.raises(error) as caught:
            provider.generate(VisionRequest(None, "private transcript"))
        assert len(calls) == expected_calls
        assert len(sleeps) == expected_calls - 1
        public_output = str(caught.value) + caplog.text
        for secret in ("fake-private-key", "private transcript", "sensitive body"):
            assert secret not in public_output
    finally:
        provider.close()
