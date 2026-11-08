# Vidsight

Vidsight is a Python toolkit for analyzing YouTube videos from timestamped
transcripts and sampled frames. It provides configurable AI providers, STT
backends, a CLI, and an MCP server over stdio.

![Stars](https://img.shields.io/github/stars/Songjag/Vidsight-YouTube-Analysis-Skill?style=flat&label=stars)
![Watchers](https://img.shields.io/github/watchers/Songjag/Vidsight-YouTube-Analysis-Skill?style=flat&label=watchers)

> Languages: [Tiếng Việt](./vie.md) · [中文](./cn.md) · [日本語](./jp.md)

Architecture: [diagram and implementation notes](./architecture.md).

Real test activity: [YouTube analysis test](./test-activity.md).

## Features

- Analyze a video or a bounded time range.
- Combine subtitles/STT with sampled frames when vision is explicitly enabled.
- Preserve original timestamps and report extracted and submitted frames.
- Select providers through environment variables without changing the pipeline.
- Support OpenAI, Anthropic, Gemini, OpenAI-compatible endpoints, Ollama, and
  optional GGUF inference.
- Expose `watch_video_overview`, `analyze_video_segment`, and
  `ask_video_question` as MCP tools.
- Return a raw timeline when `LLM_PROVIDER=auto` finds no valid provider.

Vidsight does not claim continuous viewing when it only sends sampled frames.
Results include evidence sources and warnings.

## Requirements and installation

- Python 3.11 or newer.
- `ffmpeg` in `PATH` for audio extraction.
- `uv` is recommended.

```sh
uv sync
uv run vidsight doctor
uv run pytest -q
uv run ruff check .
```

Create a private `.env` from `.env.example`. Never commit `.env` or paste an API
key into an issue or chat.

## CLI

```sh
uv run vidsight --env-file .env analyze \
  'https://www.youtube.com/watch?v=VIDEO_ID' \
  --question 'What is the main topic?' --start 0 --end 60
```

Require visual evidence with `--require-vision`:

```sh
uv run vidsight --env-file .env analyze \
  'https://www.youtube.com/watch?v=VIDEO_ID' \
  --question 'What action is visible?' --start 0 --end 60 \
  --require-vision
```

`doctor` validates configuration offline. Its `network_checked=false` and
`model_inference_tested=false` fields do not prove endpoint connectivity.

## Configuration

Non-empty `LLM_*` values take precedence over matching legacy variables, and
process variables take precedence over `.env`. Empty generic values do not erase
legacy keys or models.

```dotenv
LLM_PROVIDER=auto
LLM_MODEL=
LLM_TIMEOUT_SEC=180
LLM_MAX_RETRIES=3
LLM_MAX_IMAGES=12
LLM_IMAGE_MAX_SIDE=1024
LLM_ALLOW_CLOUD=true
LLM_NATIVE_VIDEO=false
STT_PROVIDER=auto
```

Explicit providers fail fast when required configuration is missing. `auto`
selects one valid provider at initialization and never switches after a request
failure. `none` disables the LLM. If no provider is valid, overview returns a
raw timeline.

### Provider examples

```dotenv
# Gemini
LLM_PROVIDER=gemini
GEMINI_API_KEY=<private-key>
LLM_MODEL=<verified-model>
# Enable only after verifying image support.
LLM_SUPPORTS_IMAGES=true
```

```dotenv
# OpenAI-compatible local server
LLM_PROVIDER=openai_compatible
LLM_BASE_URL=http://127.0.0.1:1234/v1
LLM_MODEL=<loaded-model>
LLM_ALLOW_CLOUD=false
```

```dotenv
# Ollama
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=<loaded-model>
LLM_ALLOW_CLOUD=false
```

For Anthropic use `ANTHROPIC_API_KEY`; for OpenAI use `OPENAI_API_KEY`.

GGUF is optional:

```sh
uv sync --extra local
```

```dotenv
LLM_PROVIDER=gguf
GGUF_MODEL_PATH=/models/model.gguf
LLM_ALLOW_CLOUD=false
```

GGUF does not download models. Vision requires an explicitly supported handler
and projector file; the automatic handler is text-only.

## MCP server

```sh
uv run vidsight --env-file yourpath/Vidsight/.env serve
```

The server uses JSON-RPC on stdin/stdout. Restart it after changing `.env`.

| Tool | Parameters |
|---|---|
| `watch_video_overview` | `url: str` |
| `analyze_video_segment` | `url`, `start`, `end`, `question`, `require_vision=false` |
| `ask_video_question` | `url`, `question`, `require_vision=false` |

Results contain `source`, `timeline`, `frame_timestamps`,
`submitted_frame_timestamps`, `analysis`, and `warnings`. Errors have
`isError=true` and sanitized `error.code`/`error.message`.

See [the MCP specification](./mcp-proposal.md).

## Evidence, limits, and privacy

- Vision is never inferred from a provider name alone; unknown models are
  text-only by default.
- Images carry MIME type and original timestamps and are resized to the
  configured limit.
- `frame_timestamps` are extracted frames; `submitted_frame_timestamps` are
  the frames remaining after request budgeting.
- Videos are limited to one hour and the download target is 500 MB.
- `LLM_ALLOW_CLOUD=false` blocks remote AI endpoints; fetching YouTube still
  requires network access.
- Logs and public errors exclude API keys, authorization headers, full
  transcripts, images, and raw provider bodies.
- Native video upload is not implemented; Vidsight uses sampled frames.

## STT and testing

Subtitle retrieval is preferred. Depending on configuration, Vidsight can use
Groq Whisper, OpenAI-compatible transcription, or local `faster-whisper`.

```sh
uv sync --extra stt-local
uv run pytest -q
uv run ruff check .
uv run vidsight doctor
```

The default tests use mock HTTP, fake local models, and generated media
fixtures. Real provider or YouTube smoke tests are separate from CI and must be
reported as `PASS`, `FAIL`, or `NOT TESTED`.

See [development notes](./development.md). The project uses the MIT License
when a `LICENSE` file is provided by the repository.
