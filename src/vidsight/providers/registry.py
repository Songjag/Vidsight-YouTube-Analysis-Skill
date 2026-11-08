from .base import VisionProvider
from .config import ProviderConfig, SPECS, validate_url


def create_provider(config: ProviderConfig | None, **kwargs) -> VisionProvider | None:
    if config is None:
        return None
    if config.provider != "gguf":
        validate_url(config.base_url, config.allow_cloud)
    from .protocols.openai_chat import OpenAIChatProvider
    from .protocols.anthropic import AnthropicProvider
    from .protocols.gemini import GeminiProvider
    from .protocols.ollama_native import OllamaProvider
    from .protocols.gguf_inproc import GGUFProvider
    adapters = {"openai_chat": OpenAIChatProvider, "anthropic": AnthropicProvider,
                "gemini": GeminiProvider, "ollama_native": OllamaProvider,
                "gguf_inproc": GGUFProvider}
    return adapters[SPECS[config.provider].protocol](config, **kwargs)
