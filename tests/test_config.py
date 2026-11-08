import pytest

from vidsight.providers.base import ConfigurationError
from vidsight.providers.config import resolve_config, validate_url


def test_no_provider():
    assert resolve_config({}) is None
    assert resolve_config({"LLM_PROVIDER": "none"}) is None


def test_legacy_and_precedence():
    env = {"LLM_PROVIDER": "openai", "OPENAI_API_KEY": "secret", "OPENAI_MODEL": "chosen"}
    assert resolve_config(env).model == "chosen"
    assert resolve_config({**env, "LLM_API_KEY": ""}).api_key == "secret"
    cfg = resolve_config({**env, "LLM_MODEL": "override"})
    assert cfg.model == "override"
    assert cfg.diagnostics == ("LLM_MODEL takes precedence over OPENAI_MODEL",)
    assert "secret" not in repr(cfg)


@pytest.mark.parametrize("env", [
    {"LLM_PROVIDER": "wrong"}, {"LLM_PROVIDER": "openai"},
    {"LLM_PROVIDER": "ollama"},
    {"LLM_PROVIDER": "ollama", "LLM_MODEL": "m", "LLM_MAX_IMAGES": "0"},
    {"LLM_PROVIDER": "ollama", "LLM_MODEL": "m", "LLM_TIMEOUT_SEC": "nan"},
    {"LLM_PROVIDER": "ollama", "LLM_MODEL": "m", "LLM_MAX_RETRIES": "1.5"},
    {"LLM_PROVIDER": "ollama", "LLM_MODEL": "m", "LLM_NATIVE_VIDEO": "true"},
])
def test_fail_fast(env):
    with pytest.raises(ConfigurationError):
        resolve_config(env)


@pytest.mark.parametrize("url", ["https://user:key@host/v1", "https://host?key=secret",
                                    "file:///tmp/x", "https://host#key", "http://host:bad"])
def test_invalid_url(url):
    with pytest.raises(ConfigurationError):
        validate_url(url, True)


def test_local_policy_and_auto_order():
    env = {"OPENAI_API_KEY": "k", "OPENAI_MODEL": "m", "OLLAMA_BASE_URL": "http://localhost:11434",
           "OLLAMA_MODEL": "local"}
    assert resolve_config(env).provider == "openai"
    assert resolve_config({**env, "LLM_ALLOW_CLOUD": "false"}).provider == "ollama"
    with pytest.raises(ConfigurationError):
        resolve_config({**env, "LLM_PROVIDER": "openai", "LLM_ALLOW_CLOUD": "false"})
    with pytest.raises(ConfigurationError):
        validate_url("http://192.168.1.2:11434", False)
