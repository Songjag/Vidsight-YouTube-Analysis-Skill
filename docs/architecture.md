# Vidsight Architecture

Sơ đồ dưới đây mô tả pipeline đang có trong repository. Vidsight lấy video và
phụ đề từ YouTube, trích xuất frame/audio, chuẩn hóa evidence rồi gửi một
request tới provider đã được chọn lúc khởi tạo.

```mermaid
%%{init: {
  "theme": "dark",
  "themeVariables": {
    "primaryColor": "#444444",
    "primaryTextColor": "#ffffff",
    "primaryBorderColor": "#999999",
    "lineColor": "#aaaaaa",
    "secondaryColor": "#333333",
    "tertiaryColor": "#222222",
    "clusterBkg": "#292929",
    "clusterBorder": "#777777"
  }
}}%%

flowchart TD
    User["AI Agent / User"] -->|MCP / CLI| Entry["MCP Server / CLI"]

    subgraph Pipeline["Vidsight Analysis Pipeline"]
        Entry --> Analyzer["VideoAnalyzer"]
        Analyzer --> Config["Config + Provider Registry"]

        Analyzer --> Download["YouTube Downloader<br/>yt-dlp"]
        Download --> Video["Video File"]
        Download --> Subtitles["YouTube Subtitles"]

        Video --> Frames["Frame Extraction<br/>OpenCV + JPEG"]
        Video --> Audio["Audio Extraction<br/>ffmpeg"]

        Audio --> STT["STT Registry"]
        Subtitles --> Transcript["Timestamped Transcript"]
        STT --> Transcript

        Frames --> Evidence["Multimodal Evidence<br/>frames + transcript"]
        Transcript --> Evidence
    end

    subgraph Providers["AI Provider Protocols"]
        Config --> OpenAI["OpenAI Chat<br/>OpenAI-compatible"]
        Config --> Anthropic["Anthropic Messages"]
        Config --> Gemini["Google Gemini<br/>generateContent"]
        Config --> Ollama["Ollama Native"]
        Config --> GGUF["Optional GGUF<br/>llama-cpp-python"]
    end

    Evidence --> OpenAI
    Evidence --> Anthropic
    Evidence --> Gemini
    Evidence --> Ollama
    Evidence --> GGUF

    OpenAI --> Response["VisionResponse"]
    Anthropic --> Response
    Gemini --> Response
    Ollama --> Response
    GGUF --> Response

    Response --> Output["Structured Result<br/>source, timeline,<br/>timestamps, analysis, warnings"]
    Analyzer -->|No valid provider| Raw["Raw Timeline<br/>analysis = null"]
    Raw --> Output
```

## Luồng xử lý

1. `MCP Server` hoặc CLI tạo `VideoAnalyzer`.
2. `Config` validate policy, model, endpoint và chọn provider một lần.
3. `yt-dlp` tải video; subtitle YouTube được ưu tiên cho transcript.
4. Vidsight trích frame bằng OpenCV và audio bằng `ffmpeg` khi cần STT.
5. Evidence giữ timestamp gốc và được giới hạn theo capability/budget.
6. Registry gọi đúng adapter đã chọn; request lỗi không fallback sang provider
   khác.
7. Kết quả trả `source`, `timeline`, `frame_timestamps`,
   `submitted_frame_timestamps`, `analysis` và `warnings`.

## Các điểm quan trọng

- Model chưa được xác nhận vision sẽ được xem là text-only.
- Native video upload chưa triển khai; pipeline hiện dùng sampled frames.
- `LLM_PROVIDER=auto` chỉ fallback về raw timeline khi không có provider hợp lệ
  lúc khởi tạo; không fallback sau lỗi request.
- `LLM_ALLOW_CLOUD=false` chặn remote AI endpoint, nhưng việc lấy nội dung từ
  YouTube vẫn cần network.
- Log và lỗi public không chứa API key, authorization header, transcript đầy đủ,
  ảnh hoặc raw provider body.

## Source chính

- [`VideoAnalyzer`](../src/vidsight/core/orchestrator.py)
- [`Provider Registry`](../src/vidsight/providers/registry.py)
- [`Provider Configuration`](../src/vidsight/providers/config.py)
- [`Gemini Provider`](../src/vidsight/providers/protocols/gemini.py)
- [`YouTube Media`](../src/vidsight/media/youtube.py)
- [`MCP Server`](../src/vidsight/mcp_server.py)
