"""Lazy GGUF runtime. One model instance; calls and close protected by a lock."""
import importlib
import json
from dataclasses import replace
from threading import Lock

from ...media.frames import prepare_request
from ..base import ConfigurationError, ProviderResponseError, VisionRequest, VisionResponse
from ..config import ProviderConfig
from .openai_chat import messages


class GGUFProvider:
    def __init__(self, config: ProviderConfig):
        self.config = config
        self._model = None
        self._handler = None
        self._lock = Lock()

    def _load(self) -> None:
        try:
            backend = importlib.import_module("llama_cpp")
        except ImportError:
            raise ConfigurationError("gguf: install optional backend with uv sync --extra local") from None
        try:
            if self.config.capabilities.supports_images:
                handlers = importlib.import_module("llama_cpp.llama_chat_format")
                self._handler = handlers.Llava15ChatHandler(clip_model_path=self.config.mmproj_path,
                                                           verbose=False)
            self._model = backend.Llama(model_path=self.config.model_path,
                                         n_ctx=self.config.capabilities.context_tokens,
                                         n_gpu_layers=self.config.n_gpu_layers,
                                         chat_handler=self._handler, verbose=False)
        except Exception:
            self._release()
            raise ConfigurationError("gguf: model/handler load failed; verify files and compatible runtime") from None

    def generate(self, request: VisionRequest) -> VisionResponse:
        if self.config.json_mode and request.response_format is None:
            request = replace(request, response_format="json_object")
        request, warnings = prepare_request(request, self.config.capabilities)
        with self._lock:
            if self._model is None:
                self._load()
            options = {"messages": messages(request), "max_tokens": request.max_tokens, "stream": False}
            if request.temperature is not None:
                options["temperature"] = request.temperature
            if request.response_format:
                options["response_format"] = {"type": request.response_format}
            try:
                data = self._model.create_chat_completion(**options)
                choice = data["choices"][0]
                text = choice["message"]["content"]
                if not isinstance(text, str) or not text.strip():
                    raise ValueError("empty")
                truncated = choice.get("finish_reason") != "stop"
            except Exception:
                raise ProviderResponseError("gguf: generation failed or returned malformed response") from None
        valid = None
        if request.response_format:
            try:
                json.loads(text)
                valid = True
            except ValueError:
                valid = False
        return VisionResponse(text, self.config.provider, self.config.model,
                              warnings=warnings, truncated=truncated, valid_json=valid)

    def _release(self) -> None:
        try:
            if self._model is not None:
                self._model.close()
        finally:
            self._model = None
            handler, self._handler = self._handler, None
            if handler is not None and hasattr(handler, "close"):
                handler.close()

    def close(self) -> None:
        with self._lock:
            self._release()
