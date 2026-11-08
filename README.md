# Vidsight

Python toolkit phân tích YouTube bằng transcript và khung hình lấy mẫu.
Repository ban đầu chỉ có skeleton; bản triển khai này thêm provider, media,
STT, pipeline, CLI và MCP Server stdio. Ba MCP tools sử dụng API mới đã được
duyệt; không tìm thấy schema cũ trong source/Git history để đối chiếu tương thích.

Tài liệu đa ngôn ngữ: [English](docs/en.md) · [Tiếng Việt](docs/vie.md) ·
[中文](docs/cn.md) · [日本語](docs/jp.md).

Kiến trúc: [docs/architecture.md](docs/architecture.md).

## Chạy bằng uv

```sh
uv sync
uv run vidsight doctor
uv run pytest -q
uv run ruff check .
```

Tạo `.env` riêng dựa trên `.env.example` rồi cấu hình provider/model.
Biến môi trường process ưu tiên hơn `.env`. `LLM_*` không rỗng ưu tiên hơn biến
legacy tương ứng, rồi đến default. Biến rỗng không xóa key/model legacy.
Không cần cài cloud SDK. `ffmpeg` phải có trong PATH để trích audio.

```sh
uv run vidsight analyze 'https://www.youtube.com/watch?v=VIDEO_ID' \
  --question 'Nội dung chính là gì?' --start 0 --end 60
# Tác vụ bắt buộc nhìn hình: lỗi nếu model chưa được xác nhận hỗ trợ vision.
uv run vidsight analyze 'https://www.youtube.com/watch?v=VIDEO_ID' \
  --question 'Hành động nào xuất hiện?' --start 0 --end 60 --require-vision
```

`doctor` chỉ validate offline; `network_checked=false` và
`model_inference_tested=false` không có nghĩa endpoint/model chạy được.

## MCP Server

```sh
uv run vidsight --env-file /absolute/path/to/Vidsight/.env serve
```

Server chờ JSON-RPC trên stdin/stdout; chạy trực tiếp sẽ không hiện menu.
Mỗi process phân tích một video tại một thời điểm trong worker thread.
Không chặn event loop; cancel chờ worker cleanup và không dừng cưỡng bức request
AI đang chạy. Đổi `.env` cần restart server. Không truyền API key trong tool call.

| Công cụ chính thức | Tham số |
|---|---|
| `watch_video_overview` | `url: str` |
| `analyze_video_segment` | `url: str, start: float, end: float, question: str, require_vision: bool = false` |
| `ask_video_question` | `url: str, question: str, require_vision: bool = false` |

`start/end` tính bằng giây gốc; `0 <= start < end <= duration`.
`require_vision=true` bắt buộc có model vision. Mỗi tool công bố mô tả,
`inputSchema` và `outputSchema`; trả `source`, timeline, timestamps, analysis và
warnings trong `structuredContent` và JSON text. Lỗi có `isError=true` và JSON
`error.code/error.message`, không biến lỗi thành timeline thành công.
Xem [đặc tả API đầy đủ](doc/mcp-proposal.md).

### Codex

Chạy `uv sync` trước. Thêm vào `~/.codex/config.toml` (đổi đường dẫn nếu clone
ở nơi khác); dùng đường dẫn executable và `.env` tuyệt đối để không phụ thuộc cwd:

```toml
[mcp_servers.vidsight]
command = "/run/media/songjag/NewVolume/Vidsight/.venv/bin/vidsight"
args = ["--env-file", "/run/media/songjag/NewVolume/Vidsight/.env", "serve"]
startup_timeout_sec = 30
tool_timeout_sec = 600
```

Hoặc đăng ký qua CLI, rồi đặt `tool_timeout_sec` phù hợp trong config:

```sh
codex mcp add vidsight -- /run/media/songjag/NewVolume/Vidsight/.venv/bin/vidsight \
  --env-file /run/media/songjag/NewVolume/Vidsight/.env serve
codex mcp list
```

Mở lại phiên Codex và kiểm tra danh sách công cụ. Timeout 600 giây là cấu hình
client ví dụ, không đảm bảo mọi video xử lý xong trong khoảng đó.
Cấu trúc cấu hình được đối chiếu với [tài liệu MCP của Codex](https://learn.chatgpt.com/docs/extend/mcp?surface=cli).

### Claude Desktop

Vào Settings → Developer → Edit Config. Gộp entry sau vào `mcpServers` trong
`claude_desktop_config.json`, giữ nguyên các server khác:

```json
{
  "mcpServers": {
    "vidsight": {
      "command": "/run/media/songjag/NewVolume/Vidsight/.venv/bin/vidsight",
      "args": ["--env-file", "/run/media/songjag/NewVolume/Vidsight/.env", "serve"]
    }
  }
}
```

Đây là đường dẫn Linux của workspace này; trên macOS/Windows dùng đường dẫn
clone tương ứng (Windows executable `.venv\\Scripts\\vidsight.exe`, escape `\\`
trong JSON). Đảm bảo PATH của ứng dụng có `ffmpeg`. Restart Claude Desktop và
kiểm tra ba công cụ. Tham khảo [hướng dẫn MCP local chính thức](https://modelcontextprotocol.io/docs/develop/connect-local-servers).
Đã kiểm thử giao thức bằng MCP SDK/stdin/stdout; chưa chạy thử GUI Codex hoặc
Claude Desktop, và chưa tự chỉnh cấu hình client trên máy người dùng.

## Provider

| Cấu hình | Adapter | Mức kiểm chứng |
|---|---|---|
| `openai`, `openai_compatible` | Chat Completions | Mock HTTP |
| `anthropic` | Messages | Mock HTTP |
| `gemini` | generateContent inline images | Mock HTTP |
| `ollama` | `/api/chat`, không stream | Mock HTTP |
| `gguf` | llama-cpp-python | Fake runtime, chưa inference thật |

LM Studio, llama.cpp server, vLLM và các dịch vụ tương thích dùng
`openai_compatible`; chưa smoke test từng sản phẩm. Model phải hỗ trợ schema
Chat Completions và `max_tokens`; các model yêu cầu Responses hoặc tham số riêng
chưa được hỗ trợ. Không có provider mặc định nếu thiếu tên model.

`auto` xét OpenAI → Anthropic → Gemini → Ollama → GGUF → custom endpoint, chỉ
chọn ứng viên hợp lệ và phù hợp policy. Khi không chọn được: timeline thô.
`none` tắt LLM. Explicit sai cấu hình: lỗi. Không chuyển provider sau lỗi request.
`auto` dùng dấu hiệu key legacy, `OLLAMA_BASE_URL`, `GGUF_MODEL_PATH` hoặc
`LLM_BASE_URL`; chỉ `LLM_API_KEY` không đủ để suy ra nhà cung cấp.

Các ví dụ dưới đây là template cấu hình, **chưa phải smoke test PASS**.
Thay placeholder model bằng model bạn có quyền truy cập; xác nhận capability
trước khi bật `LLM_SUPPORTS_IMAGES`. Không gửi secret trong issue/chat.

OpenAI:

```dotenv
LLM_PROVIDER=openai
OPENAI_API_KEY=<private-key>
LLM_MODEL=<verified-model>
LLM_SUPPORTS_IMAGES=true
```

Anthropic:

```dotenv
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=<private-key>
LLM_MODEL=<verified-model>
LLM_SUPPORTS_IMAGES=true
```

Gemini:

```dotenv
LLM_PROVIDER=gemini
GEMINI_API_KEY=<private-key>
LLM_MODEL=<verified-model>
LLM_SUPPORTS_IMAGES=true
```

Custom OpenAI-compatible (LM Studio/llama.cpp/vLLM hoặc cloud):

```dotenv
LLM_PROVIDER=openai_compatible
LLM_BASE_URL=http://127.0.0.1:1234/v1
LLM_MODEL=<loaded-model>
LLM_ALLOW_CLOUD=false
# LLM_API_KEY=<key-if-required>
# LLM_SUPPORTS_IMAGES=true
```

Ollama native:

```dotenv
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=<loaded-model>
LLM_ALLOW_CLOUD=false
# LLM_SUPPORTS_IMAGES=true
```

GGUF:

```sh
uv sync --extra local
```

```dotenv
LLM_PROVIDER=gguf
GGUF_MODEL_PATH=/models/model.gguf
LLM_ALLOW_CLOUD=false
# Vision hiện chỉ triển khai Llava15ChatHandler; không tự nhận diện kiến trúc.
# LLM_SUPPORTS_IMAGES=true
# GGUF_CHAT_HANDLER=llava-1.5
# GGUF_MMPROJ_PATH=/models/mmproj.gguf
GGUF_N_CTX=8192
GGUF_N_GPU_LAYERS=0
```

`auto` handler chỉ dành cho text-only. GGUF không tự tải model; optional extra
có thể cần compiler/native libraries và Python version phù hợp.

## Evidence, ngân sách và quyền riêng tư

Không suy ra vision từ provider/model name: mặc định text-only có cảnh báo.
Ảnh có MIME và timestamp gốc, resize tối đa 1024, JPEG mặc định, không phóng to.
Lấy tối đa 12 frame, tiếp tục giảm đều theo thời gian nếu vượt context budget.
Transcript dài được lấy mẫu theo block và rút ngắn đầu/cuối với marker/cảnh báo.
Prompt và output reserve không bị cắt. Ước tính token ảnh chỉ xấp xỉ.
`frame_timestamps` là khung đã trích; `submitted_frame_timestamps` là khung gửi
đến model sau budget. Không khẳng định đã xem liên tục toàn video.

Giới hạn Vidsight: video tối đa 1 giờ, download mục tiêu ≤500 MB (giới hạn
yt-dlp không thay cho disk quota), ảnh ≤12 MiB/request. Video vẫn tải nguyên
file ngay cả khi chỉ phân tích đoạn. `raw-timeline` trả transcript chưa có AI
diễn giải. Lỗi AI không bị biến thành timeline thành công.

`LLM_ALLOW_CLOUD=false` chặn endpoint AI ngoài localhost/127.0.0.1/[::1], gồm
STT; hostname LAN không được coi là local. YouTube vẫn dùng mạng để tải vào.
HTTP AI không theo redirect, không lấy proxy từ môi trường. API URL không
được chứa userinfo/query/fragment. Chưa hỗ trợ Azure auth/api-version.
Không log key, payload, transcript hay ảnh. File tạm được cleanup, không xóa
input của người dùng. Kết quả CLI có transcript theo yêu cầu, hãy lưu riêng nếu
nội dung nhạy cảm. Không có `raw` provider response trong output.

`LLM_MAX_RETRIES=3` là tối đa 3 lần thử lại sau lần đầu cho lỗi kết nối,
408/409/425/429/5xx. Backoff có jitter và Retry-After. Retry time budget hữu hạn;
timeout HTTP là timeout từng thao tác I/O, không phải hard deadline tiến trình.
Không retry 400/401/403/404 hoặc upload STT để tránh lặp chi phí.

JSON mode cần cả `LLM_JSON_MODE=true` và `LLM_SUPPORTS_JSON_MODE=true` sau khi
xác nhận model; Anthropic JSON mode chưa triển khai. JSON lỗi giữ text và
`valid_json=false`. Native video chưa triển khai; bật cờ sẽ báo lỗi.

## STT

Ưu tiên phụ đề YouTube (vi, en), rồi backend cấu hình nếu không có đoạn phù hợp.
`STT_PROVIDER=auto`: Groq khi có key và cho phép cloud → model faster-whisper
tại `STT_MODEL_PATH` → chỉ phụ đề. Không chuyển backend sau lỗi STT.
Các lựa chọn: `none`, `youtube_subtitles`, `groq_whisper`, `openai_whisper`,
`openai_compatible`, `faster_whisper`. `none` tắt cả phụ đề và STT.

HTTP dùng WAV mono 16 kHz, verbose JSON có timestamp. Groq mặc định
`whisper-large-v3`; OpenAI mặc định `whisper-1`; custom cần `STT_BASE_URL`,
`STT_MODEL`, `STT_MAX_BYTES` đã xác minh. `STT_API_KEY` ưu tiên key legacy.
OpenAI/Groq giới hạn upload phía client 25 MB. WAV được chia tối đa 300 giây,
overlap 1 giây, tối đa 24 lượt; offset được cộng lại, loại trùng text giống hệt
trong vùng overlap. Các câu diễn đạt khác nhau ở ranh giới vẫn có thể trùng ý.
Kết quả báo số lượt; mỗi lượt cloud có thể tính phí.

```sh
uv sync --extra stt-local
```

Model local phải có sẵn qua `STT_MODEL_PATH`; không tự download. whisper.cpp
chưa có adapter. Âm thanh hiện được dùng qua STT, không gửi trực tiếp vào vision LLM.

## Kiểm chứng và tài liệu

Test mặc định chặn kết nối socket, dùng MockTransport/fake model và fixture
video tạo bằng ffmpeg. Xem [audit và tiến độ](doc/development.md).
Smoke test cloud-native, OpenAI-compatible, local server, GGUF vision và YouTube
đều **NOT TESTED** vì chưa có model/server/key/video đầu vào để chạy thử.

Tài liệu giao thức đã đối chiếu:
[OpenAI Chat Completions](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create),
[Anthropic Messages](https://platform.claude.com/docs/en/api/messages/create),
[Gemini generateContent](https://ai.google.dev/api/generate-content),
[Ollama chat](https://docs.ollama.com/api/chat),
[llama-cpp-python](https://llama-cpp-python.readthedocs.io/en/latest/),
[Groq STT](https://console.groq.com/docs/speech-to-text),
[youtube-transcript-api](https://github.com/jdepoix/youtube-transcript-api).
