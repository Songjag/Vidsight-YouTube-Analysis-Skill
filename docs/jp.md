# Vidsight

Vidsight は、タイムスタンプ付きの字幕・文字起こしとサンプリングした動画
フレームを使って YouTube 動画を分析する Python ツールキットです。設定可能な
AI provider、STT バックエンド、CLI、stdio MCP server を提供します。

![Stars](https://img.shields.io/github/stars/Songjag/Vidsight-YouTube-Analysis-Skill?style=flat&label=stars)
![Watchers](https://img.shields.io/github/watchers/Songjag/Vidsight-YouTube-Analysis-Skill?style=flat&label=watchers)

> 言語: [English](./en.md) · [Tiếng Việt](./vie.md) · [中文](./cn.md)

## 機能

- 動画全体または指定した時間範囲を分析します。
- vision 対応を確認したモデルでは、字幕/STT とサンプリング画像を組み合わせます。
- 元のタイムスタンプを保持し、抽出フレームと送信フレームを区別します。
- 環境変数で AI provider を選択でき、pipeline の変更は不要です。
- OpenAI、Anthropic、Gemini、OpenAI-compatible endpoint、Ollama、
  オプションの GGUF 推論に対応します。
- `watch_video_overview`、`analyze_video_segment`、`ask_video_question` の
  3 つの MCP tool を提供します。
- `LLM_PROVIDER=auto` で有効な provider がない場合は raw timeline を返します。

サンプリングしたフレームだけを送った場合、動画全体を連続視聴したとは主張
しません。結果には証拠の種類と警告が含まれます。

## 必要条件とインストール

- Python 3.11 以上。
- 音声抽出には `PATH` に `ffmpeg` が必要です。
- `uv` の使用を推奨します。

```sh
uv sync
uv run vidsight doctor
uv run pytest -q
uv run ruff check .
```

`.env.example` から非公開の `.env` を作成してください。`.env` を commit
したり、API key を issue やチャットに貼り付けたりしないでください。

## CLI

```sh
uv run vidsight --env-file .env analyze \
  'https://www.youtube.com/watch?v=VIDEO_ID' \
  --question '主な内容は何ですか？' --start 0 --end 60
```

画像による証拠を必須にする場合は `--require-vision` を使います。

```sh
uv run vidsight --env-file .env analyze \
  'https://www.youtube.com/watch?v=VIDEO_ID' \
  --question '画面上で何が起きていますか？' --start 0 --end 60 \
  --require-vision
```

`doctor` はオフラインで設定を検証するだけです。
`network_checked=false` と `model_inference_tested=false` は endpoint の接続成功
を意味しません。

## 設定

空でない `LLM_*` は対応する legacy 変数より優先され、プロセス環境変数は
`.env` より優先されます。空の generic 値が legacy key/model を消すことはありません。

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

明示的な provider の必須設定がない場合は即時にエラーになります。`auto` は
初期化時に一つの有効な provider を選び、request 失敗後に切り替えません。
`none` は LLM を無効にします。有効な provider がなければ raw timeline を返します。

### Provider の例

```dotenv
# Gemini
LLM_PROVIDER=gemini
GEMINI_API_KEY=<private-key>
LLM_MODEL=<verified-model>
# model の画像対応を確認してから有効化します。
LLM_SUPPORTS_IMAGES=true
```

```dotenv
# ローカル OpenAI-compatible server
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

Anthropic は `ANTHROPIC_API_KEY`、OpenAI は `OPENAI_API_KEY` を使用します。

GGUF はオプションです。

```sh
uv sync --extra local
```

```dotenv
LLM_PROVIDER=gguf
GGUF_MODEL_PATH=/models/model.gguf
LLM_ALLOW_CLOUD=false
```

GGUF は model を自動ダウンロードしません。Vision には対応 handler と
projector ファイルが必要で、auto handler は text-only 用です。

## MCP server

```sh
uv run vidsight --env-file yourpath/Vidsight/.env serve
```

server は stdin/stdout で JSON-RPC を使用します。`.env` を変更した後は
server を再起動してください。

| Tool | 引数 |
|---|---|
| `watch_video_overview` | `url: str` |
| `analyze_video_segment` | `url`, `start`, `end`, `question`, `require_vision=false` |
| `ask_video_question` | `url`, `question`, `require_vision=false` |

結果には `source`、`timeline`、`frame_timestamps`、
`submitted_frame_timestamps`、`analysis`、`warnings` が含まれます。エラーは
`isError=true` と安全化された `error.code/error.message` を返します。

[MCP 仕様](./mcp-proposal.md)を参照してください。

## 証拠、制限、プライバシー

- provider 名だけから vision 対応とは判断せず、未知の model は text-only が
  既定です。
- 画像には MIME と元のタイムスタンプが付き、設定サイズに縮小されます。
- `frame_timestamps` は抽出フレーム、`submitted_frame_timestamps` は budget
  後に model へ送るフレームです。
- 動画は最大 1 時間、ダウンロード目標は 500 MB です。
- `LLM_ALLOW_CLOUD=false` はリモート AI endpoint を禁止しますが、YouTube
  の取得にはネットワークが必要です。
- ログや公開エラーに API key、authorization header、完全な transcript、画像、
  provider の raw body は含まれません。
- native video upload は未実装で、サンプリングフレームを使用します。

## STT とテスト

字幕を優先します。設定に応じて Groq Whisper、OpenAI-compatible transcription、
または local `faster-whisper` を使用できます。

```sh
uv sync --extra stt-local
uv run pytest -q
uv run ruff check .
uv run vidsight doctor
```

標準テストは mock HTTP、fake local model、生成した media fixture を使い、
外部サービスへ接続しません。実際の provider/YouTube smoke test は CI とは
別に実施し、`PASS`、`FAIL`、`NOT TESTED` を明記してください。

[開発ノート](./development.md)も参照してください。repository に `LICENSE`
ファイルがある場合、プロジェクトは MIT License で配布されます。
