# Vidsight

Vidsight là bộ công cụ Python phân tích video YouTube bằng transcript có mốc
thời gian và khung hình lấy mẫu. Dự án có AI provider, backend STT, CLI và MCP
server chạy qua stdio.

> Ngôn ngữ: [English](./en.md) · [中文](./cn.md) · [日本語](./jp.md)

Kiến trúc: [sơ đồ và ghi chú triển khai](./architecture.md).

## Tính năng

- Phân tích toàn bộ video hoặc một khoảng thời gian giới hạn.
- Kết hợp phụ đề/STT với khung hình khi vision được bật và xác nhận rõ ràng.
- Giữ timestamp gốc và báo khung đã trích xuất cũng như khung gửi model.
- Chọn provider bằng biến môi trường mà không sửa pipeline.
- Hỗ trợ OpenAI, Anthropic, Gemini, OpenAI-compatible, Ollama và GGUF tùy chọn.
- Cung cấp ba MCP tools: `watch_video_overview`,
  `analyze_video_segment`, `ask_video_question`.
- Nếu `LLM_PROVIDER=auto` không tìm được provider hợp lệ, trả timeline thô.

Vidsight không tuyên bố đã xem liên tục toàn video nếu chỉ gửi khung hình lấy
mẫu. Kết quả luôn có nguồn bằng chứng và cảnh báo.

## Yêu cầu và cài đặt

- Python 3.11 trở lên.
- `ffmpeg` trong `PATH` để trích xuất audio.
- Khuyến nghị dùng `uv`.

```sh
uv sync
uv run vidsight doctor
uv run pytest -q
uv run ruff check .
```

Tạo `.env` riêng từ `.env.example`. Không commit `.env` hoặc gửi API key trong
issue/chat.

## CLI

```sh
uv run vidsight --env-file .env analyze \
  'https://www.youtube.com/watch?v=VIDEO_ID' \
  --question 'Nội dung chính là gì?' --start 0 --end 60
```

Dùng `--require-vision` khi bắt buộc có bằng chứng hình ảnh:

```sh
uv run vidsight --env-file .env analyze \
  'https://www.youtube.com/watch?v=VIDEO_ID' \
  --question 'Có hành động nào nhìn thấy?' --start 0 --end 60 \
  --require-vision
```

`doctor` chỉ validate cấu hình offline. `network_checked=false` và
`model_inference_tested=false` không chứng minh endpoint đang kết nối được.

## Cấu hình

`LLM_*` không rỗng được ưu tiên hơn biến legacy tương ứng; biến môi trường
process được ưu tiên hơn `.env`. Biến generic rỗng không xóa key/model legacy.

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

Provider explicit thiếu cấu hình sẽ fail fast. `auto` chọn một provider hợp lệ
khi khởi tạo và không chuyển provider sau request lỗi. `none` tắt LLM. Nếu
không có provider hợp lệ, overview trả timeline thô.

### Ví dụ provider

```dotenv
# Gemini
LLM_PROVIDER=gemini
GEMINI_API_KEY=<private-key>
LLM_MODEL=<verified-model>
# Chỉ bật sau khi xác nhận model nhận ảnh.
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

Anthropic dùng `ANTHROPIC_API_KEY`; OpenAI dùng `OPENAI_API_KEY`.

GGUF là tùy chọn:

```sh
uv sync --extra local
```

```dotenv
LLM_PROVIDER=gguf
GGUF_MODEL_PATH=/models/model.gguf
LLM_ALLOW_CLOUD=false
```

GGUF không tự tải model. Vision cần handler và projector được hỗ trợ rõ ràng;
handler tự động chỉ dành cho text-only.

## MCP server

```sh
uv run vidsight --env-file /absolute/path/to/Vidsight/.env serve
```

Server dùng JSON-RPC trên stdin/stdout. Sau khi đổi `.env`, cần restart server.

| Tool | Tham số |
|---|---|
| `watch_video_overview` | `url: str` |
| `analyze_video_segment` | `url`, `start`, `end`, `question`, `require_vision=false` |
| `ask_video_question` | `url`, `question`, `require_vision=false` |

Kết quả có `source`, `timeline`, `frame_timestamps`,
`submitted_frame_timestamps`, `analysis` và `warnings`. Lỗi có `isError=true`
và `error.code/error.message` đã được làm sạch.

Xem [đặc tả MCP](./mcp-proposal.md).

## Bằng chứng, giới hạn và quyền riêng tư

- Không suy ra vision chỉ từ tên provider; model chưa biết mặc định text-only.
- Ảnh có MIME và timestamp gốc, được resize theo giới hạn cấu hình.
- `frame_timestamps` là khung đã trích; `submitted_frame_timestamps` là khung
  còn lại sau budget request.
- Video tối đa một giờ và mục tiêu tải xuống tối đa 500 MB.
- `LLM_ALLOW_CLOUD=false` chặn AI endpoint từ xa; lấy video YouTube vẫn cần mạng.
- Log/lỗi công khai không chứa API key, authorization header, transcript đầy đủ,
  ảnh hoặc raw body provider.
- Native video upload chưa triển khai; Vidsight dùng sampled frames.

## STT và kiểm thử

Vidsight ưu tiên phụ đề. Tùy cấu hình, có thể dùng Groq Whisper,
OpenAI-compatible transcription hoặc `faster-whisper` local.

```sh
uv sync --extra stt-local
uv run pytest -q
uv run ruff check .
uv run vidsight doctor
```

Test mặc định dùng mock HTTP, fake local model và media fixture được tạo tự động.
Smoke test thật với provider/YouTube nằm ngoài CI và phải ghi `PASS`, `FAIL` hoặc
`NOT TESTED`.

Xem [ghi chú phát triển](./development.md). Dự án dùng MIT License khi repository
cung cấp file `LICENSE`.
