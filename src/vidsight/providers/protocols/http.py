"""Finite retries and safe errors shared by HTTP protocols."""
import json
import logging
import random
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Callable
from urllib.parse import urlsplit

import httpx

from ..base import (AuthenticationError, ProviderError, ProviderResponseError,
                    ProviderTimeoutError, RateLimitError, VisionRequest, VisionResponse)
from ..config import ProviderConfig


class HTTPProvider:
    def __init__(self, config: ProviderConfig, *, transport: httpx.BaseTransport | None = None,
                 sleep: Callable[[float], None] = time.sleep):
        self.config = config
        self.client = httpx.Client(transport=transport, timeout=config.timeout,
                                   follow_redirects=False, trust_env=False)
        self.sleep = sleep
        self._logged = False

    def close(self) -> None:
        self.client.close()

    def post(self, path: str, headers: dict, payload: dict) -> dict:
        if not self._logged:
            logging.getLogger(__name__).info("AI destination host=%s; data=text/images",
                                             urlsplit(self.config.base_url).hostname)
            self._logged = True
        deadline = time.monotonic() + self.config.timeout
        for attempt in range(self.config.max_retries + 1):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ProviderTimeoutError(f"{self.config.provider}: retry time budget exceeded")
            delay = min(2 ** attempt + random.random(), 20)
            try:
                response = self.client.post(self.config.base_url + path, headers=headers,
                                            json=payload, timeout=remaining)
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                error = ProviderTimeoutError if isinstance(exc, httpx.TimeoutException) else ProviderResponseError
                failure = error(f"{self.config.provider}: connection/timeout; check endpoint availability")
                # Do not retain httpx exceptions containing request URLs/headers as public causes.
            else:
                status = response.status_code
                if 200 <= status < 300:
                    try:
                        data = response.json()
                    except ValueError:
                        raise ProviderResponseError(f"{self.config.provider}: invalid JSON response") from None
                    if not isinstance(data, dict):
                        raise ProviderResponseError(f"{self.config.provider}: expected response object")
                    return data
                error = AuthenticationError if status in {401, 403} else RateLimitError if status == 429 else ProviderResponseError
                failure = error(f"{self.config.provider}: HTTP {status}; check credentials, model and endpoint")
                if status not in {408, 409, 425, 429} and not 500 <= status < 600:
                    raise failure
                retry_after = response.headers.get("Retry-After", "")
                if retry_after:
                    try:
                        delay = max(0, float(retry_after))
                    except ValueError:
                        try:
                            date = parsedate_to_datetime(retry_after)
                            delay = max(0, (date - datetime.now(timezone.utc)).total_seconds())
                        except (ValueError, TypeError, OverflowError):
                            pass  # Malformed server hint: retain bounded backoff.
            if attempt == self.config.max_retries:
                raise failure
            if not 0 <= delay < deadline - time.monotonic():
                raise ProviderTimeoutError(f"{self.config.provider}: Retry-After exceeds time budget")
            self.sleep(delay)
        raise ProviderError("Unreachable retry state")

    def generate(self, request: VisionRequest) -> VisionResponse:
        from ...media.frames import prepare_request
        if self.config.json_mode and request.response_format is None:
            from dataclasses import replace
            request = replace(request, response_format="json_object")
        request, warnings = prepare_request(request, self.config.capabilities)
        path, headers, payload = self.encode(request)
        data = self.post(path, headers, payload)
        try:
            text, usage, truncated = self.decode(data)
            if not isinstance(text, str) or not text.strip():
                raise ValueError("empty")
            if usage is not None:
                usage = {k: v for k, v in usage.items() if isinstance(v, int) and not isinstance(v, bool)}
        except (KeyError, IndexError, TypeError, ValueError, AttributeError):
            raise ProviderResponseError(f"{self.config.provider}: empty or malformed response") from None
        valid = None
        if request.response_format:
            try:
                json.loads(text)
                valid = True
            except ValueError:
                valid = False
        if truncated:
            warnings += ("Provider output is incomplete (finish reason).",)
        return VisionResponse(text, self.config.provider, self.config.model, usage,
                              warnings, truncated, valid)

    def encode(self, request: VisionRequest) -> tuple[str, dict, dict]:
        raise NotImplementedError

    def decode(self, data: dict) -> tuple[str, dict | None, bool]:
        raise NotImplementedError
