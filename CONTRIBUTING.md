# Contributing to Vidsight

Thank you for helping improve Vidsight. Contributions are welcome for the
provider adapters, YouTube media pipeline, MCP tools, documentation, tests,
and developer experience.

## Before you start

1. Read the [README](README.md) and the project instructions in
   [AGENTS.md](AGENTS.md).
2. Search existing issues and pull requests before starting substantial work.
3. For a large feature or an architectural change, open an issue first so the
   design and scope can be discussed.
4. Do not include API keys, `.env` files, downloaded media, private
   transcripts, or raw provider responses in a commit.

## Development setup

Vidsight requires Python 3.11 or newer. `ffmpeg` must be available in `PATH`
for media extraction.

```sh
uv sync
cp .env.example .env
```

Configure a provider only in your local `.env`. Keep secrets out of source
files, test fixtures, logs, screenshots, and pull requests.

Optional local backends are installed explicitly:

```sh
uv sync --extra local
uv sync --extra stt-local
```

## Branches and commits

Create a focused branch from `master`:

```sh
git switch master
git pull --ff-only
git switch -c feat/short-description
```

Use a descriptive branch prefix:

| Prefix | Use |
|---|---|
| `feat/` | New functionality |
| `fix/` | Bug fixes |
| `docs/` | Documentation or skill updates |
| `test/` | Test-only changes |
| `refactor/` | Internal refactoring without intended behavior changes |

Keep commits small and use an imperative subject, for example:

```text
feat(gemini): add response usage parsing
fix(media): preserve frame timestamps after resizing
docs: clarify MCP setup
```

## Implementation guidelines

- Preserve the existing CLI, MCP tool names, parameters, and output shape
  unless the change is explicitly designed and tested.
- Prefer protocol adapters and existing registries over provider-specific
  conditionals in the orchestration layer.
- Do not silently fall back to another provider after a configured provider
  fails.
- Treat sampled frames as sampled evidence; never describe them as continuous
  video viewing.
- Keep cloud/local policy enforcement intact. `LLM_ALLOW_CLOUD=false` must
  prevent remote AI uploads.
- Sanitize errors and logs. Never expose authorization headers, API keys,
  complete sensitive transcripts, image payloads, or raw provider bodies.
- Keep optional local inference dependencies out of the default installation.
- Add or update tests for behavior changes and keep type hints consistent
  with the surrounding code.

## Testing and quality checks

Run the focused tests first, then the full checks before opening a pull
request:

```sh
uv run pytest -q
uv run ruff check .
uv run vidsight doctor
```

The default test suite must not require network access, API keys, a GPU, or a
large model. Use mocked transports and fake model handlers for provider
contracts.

Real provider or YouTube smoke tests are optional and must be clearly labeled
as real tests. Do not add them to the default CI path or create repeated
requests that could incur charges. If a real test is run, report the provider,
model, request count, evidence type, and sanitized result without recording
credentials or sensitive content.

## Pull requests

A good pull request should:

- explain the problem and the intended behavior;
- describe compatibility and configuration implications;
- include focused tests or explain why tests are not applicable;
- update directly related documentation;
- state the validation commands that were actually run;
- keep unrelated formatting or refactoring out of the diff.

Use a clear pull request title, such as:

```text
feat(gemini): improve multimodal response handling
```

Reviewers should be able to run the documented checks from a clean checkout.
Please respond to review feedback with a follow-up commit rather than
rewriting published history unless the repository maintainers request it.

## Documentation and skills

Documentation should reflect the current implementation rather than planned
features. When updating a skill, keep its frontmatter valid and ensure
examples use sanitized paths such as `yourpath` and never real credentials.

The portable skill package is in [`vidsight/`](vidsight/), while the workspace
discoverable skill is under
[`.agents/skills/vidsight-youtube-skill/`](.agents/skills/vidsight-youtube-skill/).

## Security reports

Do not disclose a suspected vulnerability, credential exposure, or private
video data in a public issue. Contact the maintainers privately with the
minimum necessary details. Revoke and rotate any credential that may have
been exposed.
