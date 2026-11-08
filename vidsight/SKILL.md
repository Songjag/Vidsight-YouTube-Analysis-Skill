---
name: vidsight-youtube-skill
description: "Use Vidsight to analyze YouTube videos with subtitles, audio transcripts, sampled frames, timestamps, Gemini or another configured AI provider, the CLI, or MCP tools. Trigger when a user provides a YouTube URL, asks to watch, listen to, summarize, or analyze a video, requests a timeline or timestamped answer, needs visual evidence, or wants to run a real Vidsight test."
argument-hint: "[YouTube URL and question]"
user-invocable: true
---

# Vidsight YouTube Analysis Skill

Use Vidsight to answer questions from evidence retrieved from a YouTube video.
Do not guess from the title, thumbnail, description, or metadata.

## Use this skill when

- Summarizing a YouTube video.
- Finding what was said, shown, or done at a timestamp.
- Creating a timeline or locating a relevant segment.
- Answering a question with speech and visual evidence.
- Verifying a claim against video evidence.
- Running a Vidsight CLI, Gemini, or MCP test.

## Vidsight MCP tools

Use only tools that are actually connected in the current session. Never invent
tool names, arguments, schemas, or successful results.

| Tool | Parameters | Purpose |
|---|---|---|
| `watch_video_overview` | `url` | Analyze the full video or return a raw timeline |
| `analyze_video_segment` | `url`, `start`, `end`, `question`, `require_vision` | Analyze a bounded range |
| `ask_video_question` | `url`, `question`, `require_vision` | Ask a question across the video |

Rules:

- Use a single YouTube video URL, not a playlist or local file.
- `question` must be non-empty and no longer than 8000 characters.
- Use `0 <= start < end <= duration`.
- Set `require_vision=true` for objects, actions, scenes, diagrams, or text
  visible on screen.
- If an MCP tool is unavailable, use the CLI only when the repository and its
  environment are available.

Successful results contain:

```text
video_id
start
end
duration
source
timeline
frame_timestamps
submitted_frame_timestamps
analysis
warnings
```

Errors have `isError=true` and sanitized `error.code` and `error.message`.
Never treat an error payload as an analysis result.

## Evidence policy

Interpret `source` exactly:

- `multimodal`: transcript or audio evidence and sampled frames were available;
- `visual-only`: sampled frames were available without speech evidence;
- `transcript-only`: transcript or STT was available without visual evidence;
- `raw-timeline`: no valid AI provider was selected; this is not AI analysis;
- `metadata-only`: content evidence was unavailable.

`frame_timestamps` are extracted frames.
`submitted_frame_timestamps` are frames sent after capability and budget
processing. A multimodal result can still use a sparse sample. Never claim
continuous viewing when only sampled frames were submitted.

For each important conclusion:

1. Use timestamped transcript evidence for spoken claims.
2. Use sampled frames for visual claims.
3. Separate observations from inferences.
4. Mention missing, sparse, truncated, or reduced evidence.
5. Never invent a quote, timestamp, object, action, or scene.

## Recommended workflow

1. Identify the URL, question, time range, evidence type, and desired detail.
2. Use `watch_video_overview` for a broad summary.
3. Use `analyze_video_segment` for a known range.
4. Use `ask_video_question` for a focused question across the video.
5. Require vision for visual claims; do not silently replace images with text.
6. Inspect `source`, `timeline`, both frame timestamp lists, `analysis`,
   `warnings`, `analysis.truncated`, and `analysis.valid_json`.
7. Stop when the evidence is sufficient; narrow the range instead of repeating
   an expensive full-video request.

Present answers using:

```text
Result: <direct answer>

Relevant timestamps:
- [00:00] <evidence-backed observation>
- [00:00–00:00] <speech, visual evidence, or both>

Evidence used: <transcript / frames / both / raw timeline>
Limitations: <sampling, missing audio, unavailable subtitles, truncation, or none>
```

## Real CLI test

When `.env` and the configured provider are available:

```sh
LLM_SUPPORTS_IMAGES=true \
.venv/bin/python -m vidsight --env-file .env analyze \
'https://www.youtube.com/watch?v=jNQXAC9IVRw' \
--question "Describe what is visible, summarize the spoken content, and provide original timestamps. Separate visual observations from transcript-based claims. State that the analysis uses sampled frames, not continuous viewing." \
--require-vision
```

Quote the URL in `zsh` because `?` may be interpreted as a wildcard.

Report test status honestly:

- `PASS`: usable evidence and AI analysis were returned;
- `FAIL`: the command ran but download, provider, or pipeline failed;
- `NOT TESTED`: credentials, network, media, or backend were unavailable.

Never print or store API keys, authorization headers, full sensitive
transcripts, raw provider bodies, or private media. Aggregate metadata such as
status, provider, model, duration, frame counts, timestamps, elapsed time, and
token usage is acceptable when it contains no secret.

## Provider and privacy rules

- `LLM_PROVIDER=auto` chooses once during initialization and never switches
  provider after a request failure.
- If no valid provider is configured, preserve the raw timeline behavior.
- `LLM_ALLOW_CLOUD=false` blocks remote AI upload; fetching YouTube may still
  require network access.
- Do not infer vision, audio, or video support from a provider name.
- Native video upload is not implemented; the current pipeline uses sampled
  frames.
- Report authentication, rate-limit, timeout, response, and capability errors
  explicitly.

## Project references

When this folder is inside the Vidsight repository:

- [Project README](../README.md)
- [Architecture](../docs/architecture.md)
- [MCP specification](../docs/mcp-proposal.md)
- [VideoAnalyzer](../src/vidsight/core/orchestrator.py)
- [MCP server](../src/vidsight/mcp_server.py)
- [Provider registry](../src/vidsight/providers/registry.py)
- [Gemini adapter](../src/vidsight/providers/protocols/gemini.py)
- [YouTube media pipeline](../src/vidsight/media/youtube.py)
