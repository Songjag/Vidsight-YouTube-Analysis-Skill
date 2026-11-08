"""CLI diagnostics are offline; they do not claim provider connectivity."""
import argparse
import importlib.util
import json
import shutil
import sys

from .core.orchestrator import VideoAnalyzer
from .providers.base import ProviderError
from .providers.config import load_environment, resolve_config
from .providers.transcription.registry import resolve_stt


def doctor(env: dict[str, str]) -> dict:
    config = resolve_config(env)
    stt = resolve_stt(env)
    diagnostics = list(config.diagnostics) if config else ["No valid provider; raw timeline mode"]
    if config and config.provider == "gguf" and importlib.util.find_spec("llama_cpp") is None:
        diagnostics.append("Missing GGUF optional dependency: uv sync --extra local")
    if stt.provider == "faster_whisper" and importlib.util.find_spec("faster_whisper") is None:
        diagnostics.append("Missing local STT dependency: uv sync --extra stt-local")
    return {
        "validation": "offline-only", "network_checked": False,
        "provider": config.provider if config else None,
        "supports_images": config.capabilities.supports_images if config else False,
        "diagnostics": diagnostics,
        "stt": stt.provider, "ffmpeg_available": shutil.which("ffmpeg") is not None,
        "gguf_dependency_available": importlib.util.find_spec("llama_cpp") is not None,
        "stt_local_dependency_available": importlib.util.find_spec("faster_whisper") is not None,
        "model_inference_tested": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(prog="vidsight")
    parser.add_argument("--env-file", default=".env")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="Validate configuration offline; no network/model inference")
    commands.add_parser("serve", help="Run the MCP server over stdio (stdout reserved for JSON-RPC)")
    analyze = commands.add_parser("analyze", help="Analyze a YouTube video")
    analyze.add_argument("url")
    analyze.add_argument("--question", default="Tóm tắt video với mốc thời gian.")
    analyze.add_argument("--start", type=float, default=0)
    analyze.add_argument("--end", type=float)
    analyze.add_argument("--require-vision", action="store_true")
    args = parser.parse_args()
    try:
        env = load_environment(args.env_file)
        if args.command == "serve":
            import anyio
            from .mcp_server import serve_stdio
            anyio.run(serve_stdio, env)
            return
        if args.command == "doctor":
            output = doctor(env)
        else:
            output = VideoAnalyzer(env).analyze(args.url, args.question, args.start, args.end, args.require_vision)
        print(json.dumps(output, ensure_ascii=False, indent=2))
    except ProviderError as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(2) from None
