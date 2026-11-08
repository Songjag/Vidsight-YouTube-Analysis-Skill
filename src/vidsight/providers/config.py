"""Parse settings without network access or implicit process environment mutation."""
import math
import os
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping
from urllib.parse import urlsplit

from dotenv import dotenv_values

from .base import Capabilities, ConfigurationError


@dataclass(frozen=True)
class ProviderSpec:
    protocol: str
    base_url: str = ""
    key_variable: str = ""


SPECS = {
    "openai": ProviderSpec("openai_chat", "https://api.openai.com/v1", "OPENAI_API_KEY"),
    "anthropic": ProviderSpec("anthropic", "https://api.anthropic.com/v1", "ANTHROPIC_API_KEY"),
    "gemini": ProviderSpec("gemini", "https://generativelanguage.googleapis.com/v1beta", "GEMINI_API_KEY"),
    "ollama": ProviderSpec("ollama_native", "http://127.0.0.1:11434"),
    "gguf": ProviderSpec("gguf_inproc"),
    "openai_compatible": ProviderSpec("openai_chat"),
}


def boolean(env: Mapping[str, str], name: str, default: bool) -> bool:
    value = env.get(name, "").strip().lower()
    if not value:
        return default
    if value not in {"true", "false", "1", "0"}:
        raise ConfigurationError(f"{name}: expected true/false")
    return value in {"true", "1"}


def number(env: Mapping[str, str], name: str, default: float, minimum: float = 0) -> float:
    try:
        value = float(env.get(name) or default)
    except ValueError:
        raise ConfigurationError(f"{name}: expected a number") from None
    if not math.isfinite(value) or value < minimum:
        raise ConfigurationError(f"{name}: value out of range")
    return value


def integer(env: Mapping[str, str], name: str, default: int, minimum: int = 0) -> int:
    value = number(env, name, default, minimum)
    if not value.is_integer():
        raise ConfigurationError(f"{name}: expected an integer")
    return int(value)


def validate_url(url: str, allow_cloud: bool) -> str:
    try:
        parsed = urlsplit(url)
        valid = (parsed.scheme in {"http", "https"} and parsed.hostname
                 and not parsed.username and not parsed.password
                 and not parsed.query and not parsed.fragment)
        parsed.port
    except ValueError:
        valid = False
    if not valid or any(c.isspace() for c in url):
        raise ConfigurationError("Invalid API base URL; require http(s), no credentials/query/fragment")
    if not allow_cloud and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ConfigurationError("LLM_ALLOW_CLOUD=false blocks remote AI endpoint")
    return url.rstrip("/")


@dataclass(frozen=True)
class ProviderConfig:
    provider: str
    model: str
    base_url: str = ""
    api_key: str = field(default="", repr=False)
    timeout: float = 180
    max_retries: int = 3
    allow_cloud: bool = True
    capabilities: Capabilities = field(default_factory=Capabilities)
    json_mode: bool = False
    model_path: str = field(default="", repr=False)
    mmproj_path: str = field(default="", repr=False)
    chat_handler: str = "auto"
    n_gpu_layers: int = 0
    diagnostics: tuple[str, ...] = ()


def load_environment(path: str | Path = ".env") -> dict[str, str]:
    return {**{k: v for k, v in dotenv_values(path).items() if v is not None}, **os.environ}


def resolve_config(env: Mapping[str, str]) -> ProviderConfig | None:
    # Validate shared policy even when auto has no candidates.
    boolean(env, "LLM_ALLOW_CLOUD", True)
    name = (env.get("LLM_PROVIDER") or "auto").strip().lower()
    if name == "none":
        return None
    if name == "auto":
        for candidate, spec in SPECS.items():
            configured = bool(env.get(spec.key_variable) if spec.key_variable else
                              env.get({"ollama": "OLLAMA_BASE_URL", "gguf": "GGUF_MODEL_PATH",
                                       "openai_compatible": "LLM_BASE_URL"}[candidate]))
            if not configured:
                continue
            try:
                return resolve_config({**env, "LLM_PROVIDER": candidate})
            except ConfigurationError as exc:
                logging.getLogger(__name__).info("auto skipped %s: %s", candidate, exc)
                continue  # Only selection-time invalid candidates, never request failures.
        return None
    if name not in SPECS:
        raise ConfigurationError("Unknown LLM_PROVIDER")
    spec = SPECS[name]
    diagnostics = []

    def pick(new: str, old: str, default: str = "") -> str:
        if env.get(new) and env.get(old) and env[new] != env[old]:
            diagnostics.append(f"{new} takes precedence over {old}")
        return (env.get(new) or env.get(old) or default).strip()

    allow = boolean(env, "LLM_ALLOW_CLOUD", True)
    key = pick("LLM_API_KEY", spec.key_variable)
    model = pick("LLM_MODEL", f"{name.upper()}_MODEL")
    model_path = env.get("GGUF_MODEL_PATH", "") if name == "gguf" else ""
    mmproj = env.get("GGUF_MMPROJ_PATH", "") if name == "gguf" else ""
    supports_images = boolean(env, "LLM_SUPPORTS_IMAGES", False)
    handler = env.get("GGUF_CHAT_HANDLER") or "auto"
    if name == "gguf":
        if not model_path or not Path(model_path).is_file():
            raise ConfigurationError("gguf: GGUF_MODEL_PATH must be an existing file")
        model = model or Path(model_path).stem
        if supports_images and (handler != "llava-1.5" or not mmproj or not Path(mmproj).is_file()):
            raise ConfigurationError("gguf vision: require GGUF_CHAT_HANDLER=llava-1.5 and existing GGUF_MMPROJ_PATH")
        if not supports_images and handler != "auto":
            raise ConfigurationError("gguf text-only requires GGUF_CHAT_HANDLER=auto")
        url = ""
    else:
        url = validate_url(pick("LLM_BASE_URL", f"{name.upper()}_BASE_URL", spec.base_url), allow)
        if spec.key_variable and not key:
            raise ConfigurationError(f"{name}: set LLM_API_KEY or {spec.key_variable}")
    if not model:
        raise ConfigurationError(f"{name}: set LLM_MODEL or {name.upper()}_MODEL")
    if boolean(env, "LLM_NATIVE_VIDEO", False):
        raise ConfigurationError("LLM_NATIVE_VIDEO is not implemented; use sampled frames")
    formats = tuple(x.strip() for x in (env.get("LLM_IMAGE_FORMATS") or "jpeg").split(","))
    if not formats or not set(formats) <= {"jpeg", "png", "webp"}:
        raise ConfigurationError("LLM_IMAGE_FORMATS: use jpeg,png,webp")
    caps = Capabilities(
        supports_images=supports_images, image_formats=formats,
        max_images_per_request=integer(env, "LLM_MAX_IMAGES", 12, 1),
        max_image_side_px=integer(env, "LLM_IMAGE_MAX_SIDE", 1024, 1),
        supports_json_mode=boolean(env, "LLM_SUPPORTS_JSON_MODE", False),
        context_tokens=integer(env, "GGUF_N_CTX" if name == "gguf" else "LLM_CONTEXT_TOKENS", 8192, 1),
    )
    json_mode = boolean(env, "LLM_JSON_MODE", False)
    if json_mode and name == "anthropic":
        raise ConfigurationError("anthropic: JSON mode is not implemented")
    if json_mode and not caps.supports_json_mode:
        raise ConfigurationError("LLM_JSON_MODE requires LLM_SUPPORTS_JSON_MODE=true")
    return ProviderConfig(name, model, url, key,
                          number(env, "LLM_TIMEOUT_SEC", 180, 0.01),
                          integer(env, "LLM_MAX_RETRIES", 3), allow, caps, json_mode,
                          model_path, mmproj, handler,
                          integer(env, "GGUF_N_GPU_LAYERS", 0, -1), tuple(diagnostics))
