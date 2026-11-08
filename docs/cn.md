# Vidsight

Vidsight 是一个 Python 工具包，用于结合带时间戳的字幕/转录文本和抽样视频
帧分析 YouTube 视频。项目提供可配置的 AI provider、STT 后端、CLI 以及
stdio MCP server。

![Stars](https://img.shields.io/github/stars/Songjag/Vidsight-YouTube-Analysis-Skill?style=flat&label=stars)
![Watchers](https://img.shields.io/github/watchers/Songjag/Vidsight-YouTube-Analysis-Skill?style=flat&label=watchers)

> 文档语言：[English](./en.md) · [Tiếng Việt](./vie.md) · [日本語](./jp.md)

## 功能

- 分析完整视频或限定时间范围。
- 在明确确认 vision 能力后，结合字幕/STT 与抽样帧。
- 保留原始时间戳，并报告提取帧和实际提交帧。
- 通过环境变量选择 provider，不需要修改 pipeline。
- 支持 OpenAI、Anthropic、Gemini、OpenAI-compatible endpoint、Ollama 和
  可选的 GGUF 推理。
- 提供 `watch_video_overview`、`analyze_video_segment` 和
  `ask_video_question` 三个 MCP 工具。
- `LLM_PROVIDER=auto` 找不到有效 provider 时返回原始 timeline。

如果只提交抽样帧，Vidsight 不会声称连续观看了整个视频。结果包含证据来源
和 warnings。

## 要求与安装

- Python 3.11 或更高版本。
- 音频提取需要 `PATH` 中有 `ffmpeg`。
- 推荐使用 `uv`。

```sh
uv sync
uv run vidsight doctor
uv run pytest -q
uv run ruff check .
```

从 `.env.example` 创建私有 `.env`。不要提交 `.env`，也不要在 issue 或聊天中
粘贴 API key。

## CLI

```sh
uv run vidsight --env-file .env analyze \
  'https://www.youtube.com/watch?v=VIDEO_ID' \
  --question '视频的主要内容是什么？' --start 0 --end 60
```

需要视觉证据时使用 `--require-vision`：

```sh
uv run vidsight --env-file .env analyze \
  'https://www.youtube.com/watch?v=VIDEO_ID' \
  --question '画面中出现了什么动作？' --start 0 --end 60 \
  --require-vision
```

`doctor` 只进行离线配置验证；`network_checked=false` 和
`model_inference_tested=false` 不表示 endpoint 一定可访问。

## 配置

非空的 `LLM_*` 值优先于对应 legacy 变量，进程环境变量优先于 `.env`。空的
generic 值不会删除 legacy key 或 model。

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

显式 provider 缺少必需配置时会立即失败。`auto` 只在初始化时选择一个有效
provider，request 失败后不会切换。`none` 会关闭 LLM。没有有效 provider 时，
overview 返回原始 timeline。

### Provider 示例

```dotenv
# Gemini
LLM_PROVIDER=gemini
GEMINI_API_KEY=<private-key>
LLM_MODEL=<verified-model>
# 仅在确认模型支持图片后启用。
LLM_SUPPORTS_IMAGES=true
```

```dotenv
# 本地 OpenAI-compatible server
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

Anthropic 使用 `ANTHROPIC_API_KEY`；OpenAI 使用 `OPENAI_API_KEY`。

GGUF 是可选功能：

```sh
uv sync --extra local
```

```dotenv
LLM_PROVIDER=gguf
GGUF_MODEL_PATH=/models/model.gguf
LLM_ALLOW_CLOUD=false
```

GGUF 不会自动下载模型。Vision 需要明确支持的 handler 和 projector 文件；
自动 handler 仅用于 text-only。

## MCP server

```sh
uv run vidsight --env-file yourpath/Vidsight/.env serve
```

server 在 stdin/stdout 上使用 JSON-RPC。修改 `.env` 后需要重启。

| 工具 | 参数 |
|---|---|
| `watch_video_overview` | `url: str` |
| `analyze_video_segment` | `url`, `start`, `end`, `question`, `require_vision=false` |
| `ask_video_question` | `url`, `question`, `require_vision=false` |

结果包含 `source`、`timeline`、`frame_timestamps`、
`submitted_frame_timestamps`、`analysis` 和 `warnings`。错误返回
`isError=true` 以及经过清理的 `error.code/error.message`。

请参阅 [MCP 规范](./mcp-proposal.md)。

## 证据、限制与隐私

- 不会仅根据 provider 名称推断 vision；未知模型默认为 text-only。
- 图片包含 MIME 类型和原始时间戳，并按配置限制缩放。
- `frame_timestamps` 是已提取的帧；`submitted_frame_timestamps` 是预算控制
  后发送给模型的帧。
- 视频最长一小时，下载目标上限为 500 MB。
- `LLM_ALLOW_CLOUD=false` 阻止远程 AI endpoint；获取 YouTube 仍需要网络。
- 日志和公开错误不会包含 API key、authorization header、完整 transcript、
  图片或 provider 原始 body。
- 尚未实现 native video upload；Vidsight 使用抽样帧。

## STT 与测试

Vidsight 优先使用字幕。根据配置，可以使用 Groq Whisper、
OpenAI-compatible transcription 或本地 `faster-whisper`。

```sh
uv sync --extra stt-local
uv run pytest -q
uv run ruff check .
uv run vidsight doctor
```

默认测试使用 mock HTTP、fake local model 和生成的 media fixture，不访问外部
服务。真实 provider 或 YouTube smoke test 独立于 CI，必须标记为 `PASS`、
`FAIL` 或 `NOT TESTED`。

参阅[开发说明](./development.md)。当 repository 提供 `LICENSE` 文件时，项目
使用 MIT License。
