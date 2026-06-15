# VDL Studio: implementation plan

This plan defines a commit-by-commit path to implement the VDL Studio terminal experience described in `docs/VDL_STUDIO_ASSESSMENT.md`.

The implementation goal is to add an interactive CLI workflow without breaking the current flag-based `vdl` usage.

## Commit convention

Use Conventional Commits:

```text
type(scope): summary
```

Recommended types:

- `docs`: documentation only.
- `test`: tests only.
- `refactor`: behavior-preserving restructuring.
- `feat`: new user-facing behavior.
- `fix`: bug fix.
- `chore`: tooling, packaging, dependency, or housekeeping.

Each commit should keep one conceptual change. Avoid combining refactors and feature behavior in the same commit unless the feature is impossible to isolate.

## Release target

Target outcome for the first VDL Studio release:

- Running `vdl` with no arguments opens an interactive terminal menu.
- Running `vdl` with existing arguments keeps current behavior.
- The menu supports:
  - `Download em lote`
  - `Gerar legendas`
  - `Gerar contexto`
  - `Consolidar em e-book`
  - `Sair`
- `Download em lote` supports:
  - Cookie/token input with format detection.
  - Plain cookie header input when the user does not provide JSON/Base64.
  - Destination path prompt.
  - Multiline URL paste.
  - Automatic filenames: `01.mp4`, `02.mp4`, ..., `NN.mp4`.
  - Queue control file under `data/.vdl-studio`.
  - Sequential processing by default.
  - Resume-safe behavior for completed jobs.

## Phase 0: safety baseline

### Commit 1

```text
docs(vdl-studio): add implementation roadmap
```

Scope:

- Add this implementation plan.
- Keep it aligned with `docs/VDL_STUDIO_ASSESSMENT.md`.

Acceptance criteria:

- The plan documents semantic commits, scope, test strategy, and sequencing.
- No runtime code changes.

Validation:

```bash
git diff -- docs/VDL_STUDIO_IMPLEMENTATION_PLAN.md
```

## Phase 1: prepare the current CLI for extension

### Commit 2

```text
test(cli): cover existing argument validation behavior
```

Scope:

- Add tests around current CLI argument combinations.
- Cover existing behavior before refactoring:
  - download mode requires output filename.
  - `--only-download` rejects processing flags.
  - `-u` rejects `-t`, `-c`, `--gpu`, and non-default `--whisper-model`.
  - `--all-contexts` rejects incompatible flags.
  - blank output directory falls back to `.`.

Acceptance criteria:

- Tests describe current behavior without requiring real downloads, OpenAI, Whisper, or `ffmpeg`.
- Tests can run locally without network.

Validation:

```bash
python -m pytest
```

Notes:

- If the repository has no test framework yet, add minimal `pytest` setup in this commit.

### Commit 3

```text
refactor(cli): isolate argument parsing and validation
```

Scope:

- Extract parser construction and argument validation out of `main()`.
- Keep behavior unchanged.
- Return a normalized args/config object that the current pipeline can consume.

Suggested structure:

```text
vdl/
  cli/
    argparse_cli.py
  core/
    validation.py
```

Acceptance criteria:

- Existing command examples still work.
- Existing validation errors remain equivalent.
- No VDL Studio menu yet.

Validation:

```bash
python -m pytest
python vdl.py --help
```

### Commit 4

```text
refactor(core): move credential parsing into reusable module
```

Scope:

- Move cookie/token parsing logic out of `vdl.py` into a reusable credential module.
- Preserve support for:
  - `VDL_TOKEN`
  - Base64 token
  - raw cookies JSON files
  - legacy supported formats
- Add safe masking helper for logs/summaries.

Suggested structure:

```text
vdl/
  core/
    credentials.py
```

Acceptance criteria:

- Current download flow still uses the same credential behavior.
- Credential values are not logged in full by new helpers.
- Unit tests cover Base64 detection, raw JSON detection, invalid Base64, and masking.

Validation:

```bash
python -m pytest
```

### Commit 5

```text
refactor(core): extract pipeline operations from script entrypoint
```

Scope:

- Move reusable operations behind callable functions/classes:
  - download video
  - extract audio
  - local transcription
  - OpenAI transcription/context
  - context consolidation
- Keep the existing CLI behavior unchanged.

Suggested structure:

```text
vdl/
  core/
    pipeline.py
  integrations/
    ytdlp.py
    ffmpeg.py
    whisper_local.py
    openai_api.py
```

Acceptance criteria:

- `vdl.py` becomes an entrypoint/orchestrator, not the owner of all business logic.
- No user-visible behavior changes.
- Tests can mock integrations cleanly.

Validation:

```bash
python -m pytest
python vdl.py --help
```

## Phase 2: define VDL Studio domain model

### Commit 6

```text
feat(studio): add batch and job domain models
```

Scope:

- Add models for:
  - `Batch`
  - `Job`
  - `JobState`
  - `JobStage`
  - `Artifact`
  - `CredentialRef`
- Include state/stage constants:
  - states: `queued`, `running`, `succeeded`, `failed`, `cancelled`, `blocked`
  - stages: `validate_input`, `resolve_credentials`, `download`, `extract_audio`, `transcribe`, `generate_context`, `generate_subtitles`, `consolidate_contexts`, `finalize`

Suggested structure:

```text
vdl/
  core/
    models.py
  jobs/
    state.py
```

Acceptance criteria:

- Models serialize to JSON.
- Models deserialize from JSON.
- Tests cover state/stage values and serialization.

Validation:

```bash
python -m pytest
```

### Commit 7

```text
feat(studio): add local state store for batches and queue
```

Scope:

- Add local JSONL-backed state files:
  - `data/.vdl-studio/batches.jsonl`
  - `data/.vdl-studio/download_queue.jsonl`
  - `data/.vdl-studio/jobs.jsonl`
- Add append/read/update helpers.
- Ensure state directory is created when needed.

Acceptance criteria:

- Queue records can be written and read.
- Updates preserve prior records or write explicit state transition records.
- State writes are resilient enough for local CLI usage.

Validation:

```bash
python -m pytest
```

Notes:

- For the first version, JSONL is acceptable. SQLite can replace this later if queue mutation becomes awkward.

### Commit 8

```text
feat(studio): generate ordered batch filenames
```

Scope:

- Add filename generation for batch URLs:
  - `01.mp4` through `NN.mp4`
  - `001.mp4` through `120.mp4` when needed
- Add overwrite detection for destination paths.

Acceptance criteria:

- 1 URL produces `01.mp4`.
- 9 URLs produce `01.mp4` through `09.mp4`.
- 12 URLs produce `01.mp4` through `12.mp4`.
- 120 URLs produce `001.mp4` through `120.mp4`.
- Existing files are detected before execution.

Validation:

```bash
python -m pytest
```

## Phase 3: build the interactive terminal shell

### Commit 9

```text
feat(studio-cli): open interactive menu when vdl has no arguments
```

Scope:

- Add VDL Studio interactive entrypoint.
- Route `vdl` with no args to the interactive menu.
- Preserve current flag-based behavior when args exist.
- Include menu options:
  - `Download em lote`
  - `Gerar legendas`
  - `Gerar contexto`
  - `Consolidar em e-book`
  - `Sair`

Suggested structure:

```text
vdl/
  cli/
    studio_cli.py
    prompts.py
```

Acceptance criteria:

- `vdl` opens the menu.
- `vdl --help` shows current help.
- Existing scripted command paths still work.
- Choosing `Sair` exits with status `0`.

Validation:

```bash
python -m pytest
python vdl.py --help
```

Manual validation:

```bash
python vdl.py
```

### Commit 10

```text
feat(studio-cli): add multiline input prompts
```

Scope:

- Add multiline paste support ending with `END`.
- Use for URL input and pasted cookie/token input.
- Normalize pasted values:
  - strip trailing whitespace
  - ignore empty URL lines
  - preserve cookie JSON content safely

Acceptance criteria:

- Pasted multiline URLs become an ordered list.
- Empty lines are ignored.
- Duplicate URLs are detected and displayed.
- User can cancel before execution.

Validation:

```bash
python -m pytest
```

Manual validation:

```bash
python vdl.py
```

### Commit 11

```text
feat(studio-cli): detect pasted cookie formats
```

Scope:

- In `Download em lote`, ask for authentication.
- Support:
  - environment `VDL_TOKEN`
  - pasted Base64
  - pasted raw cookies JSON
  - cookie file path
  - no credential
- Convert raw cookies JSON internally to the expected format.
- Mask credential values in review output.

Acceptance criteria:

- Raw cookies JSON is accepted.
- Base64 token is accepted.
- Invalid Base64 is rejected with a clear message.
- Full cookie/token is never printed back.

Validation:

```bash
python -m pytest
```

### Commit 12

```text
feat(studio-cli): prompt for destination and validate output paths
```

Scope:

- Ask destination directory for all selected operation types.
- Create directory after confirmation if missing.
- Validate write permission.
- For batch download, check generated filenames against existing files.

Acceptance criteria:

- Missing destination can be created.
- Non-writable destination blocks execution.
- Existing output filenames require confirmation or cancel.

Validation:

```bash
python -m pytest
```

## Phase 4: implement batch download queue execution

### Commit 13

```text
feat(studio): create download batch queue records
```

Scope:

- Convert selected URLs into batch/job records.
- Write queue records before starting downloads.
- Include:
  - `batch_id`
  - `job_id`
  - `position`
  - `url`
  - `output_filename`
  - `status`
  - `stage`
  - `attempt`

Acceptance criteria:

- Queue file exists before first download starts.
- Queue order matches URL order.
- Filenames match generated order.

Validation:

```bash
python -m pytest
```

### Commit 14

```text
feat(studio): run queued downloads sequentially
```

Scope:

- Process queued download jobs sequentially.
- Update job state/stage during execution.
- Reuse existing download pipeline.
- Write per-job events/logs.

Acceptance criteria:

- Successful job moves `queued -> running -> succeeded`.
- Failed job moves `queued -> running -> failed`.
- Batch can continue after failure when configured.
- Existing completed file is skipped unless overwrite is confirmed.

Validation:

```bash
python -m pytest
```

Manual validation should use a small known test URL or a mocked/local fixture. Avoid relying on private URLs for automated tests.

### Commit 15

```text
feat(studio): support queue resume after interruption
```

Scope:

- Add resume behavior for existing queue files.
- Detect completed jobs and skip them.
- Detect failed/incomplete jobs and ask whether to retry.

Acceptance criteria:

- Interrupted batch can be resumed.
- Completed downloads are not repeated by default.
- Retry increments attempt count.

Validation:

```bash
python -m pytest
```

## Phase 5: add non-download operations to the menu

### Commit 16

```text
feat(studio-cli): add guided subtitle generation flow
```

Scope:

- Add interactive flow for `Gerar legendas`.
- Ask for input file or directory.
- Ask target language and translation engine.
- Reuse `subtitles.py` logic or extracted subtitle pipeline.

Acceptance criteria:

- User can select file/directory path.
- Flow validates path before execution.
- Existing subtitle behavior remains available.

Validation:

```bash
python -m pytest
```

### Commit 17

```text
feat(studio-cli): add guided context generation flow
```

Scope:

- Add interactive flow for `Gerar contexto`.
- Ask for transcript path or local media path.
- If media path is provided, ask whether to transcribe first.
- Validate OpenAI key before context generation.

Acceptance criteria:

- Context generation is blocked when required transcript/OpenAI config is missing.
- Existing `-c` behavior remains available.

Validation:

```bash
python -m pytest
```

### Commit 18

```text
feat(studio-cli): add guided ebook consolidation flow
```

Scope:

- Add interactive flow for `Consolidar em e-book`.
- Ask for directory containing `.md` context files.
- Reuse existing `--all-contexts` behavior.

Acceptance criteria:

- Directory without `.md` files is rejected.
- OpenAI key is validated before execution.
- Existing `--all-contexts` behavior remains available.

Validation:

```bash
python -m pytest
```

## Phase 6: harden UX and observability

### Commit 19

```text
feat(studio): add final review screen before execution
```

Scope:

- Show review summary before starting each operation.
- For batch downloads, show:
  - URL count
  - destination
  - credential source/masked identity
  - generated filename range
  - execution mode
  - overwrite behavior

Acceptance criteria:

- User must explicitly confirm before execution.
- Sensitive values are masked.

Validation:

```bash
python -m pytest
```

### Commit 20

```text
feat(studio): add structured job events
```

Scope:

- Emit structured JSONL events for batch/job lifecycle.
- Include:
  - timestamp
  - batch ID
  - job ID
  - attempt
  - stage
  - level
  - message

Acceptance criteria:

- Events are written during download execution.
- Events do not expose cookies/tokens.
- Failed jobs include reason code/message.

Validation:

```bash
python -m pytest
```

### Commit 21

```text
docs(studio): document interactive CLI usage
```

Scope:

- Update README or docs with:
  - `vdl` interactive mode
  - batch download flow
  - cookie input formats
  - multiline URL input
  - queue files
  - automatic naming
  - resume behavior

Acceptance criteria:

- Documentation matches implemented behavior.
- Existing scripted CLI usage remains documented.

Validation:

```bash
python -m pytest
```

## Phase 7: packaging and compatibility

### Commit 22

```text
chore(deps): add interactive CLI dependencies
```

Scope:

- Add `questionary` or chosen prompt dependency only after the first interactive implementation proves it is needed.
- Pin to a safe compatible version range.

Acceptance criteria:

- Docker image builds.
- Local install works.
- Non-interactive CLI still works in non-TTY contexts.

Validation:

```bash
python -m pytest
docker compose build
```

Notes:

- If the implementation can stay dependency-free with acceptable UX, skip this commit.

### Commit 23

```text
fix(studio): handle non-tty environments gracefully
```

Scope:

- Detect when `vdl` is called without args in a non-interactive shell.
- Print a clear message and usage instead of hanging waiting for input.

Acceptance criteria:

- `vdl` without TTY exits clearly.
- `vdl --help` still works.
- CI does not hang.

Validation:

```bash
python -m pytest
```

## Phase 8: optional follow-up for API/frontend

These commits should not be part of the first terminal-focused release unless the CLI is already stable.

### Future commit

```text
feat(api): expose VDL Studio job endpoints
```

Scope:

- Add FastAPI service.
- Expose batch/job creation, status, and artifacts.

### Future commit

```text
feat(worker): process jobs through redis queue
```

Scope:

- Add Redis/RQ queue.
- Move execution out of API process.

### Future commit

```text
feat(web): add VDL Studio dark dashboard
```

Scope:

- Add React/Vite frontend based on the Figma static screens.

## Suggested branch strategy

Use a focused branch:

```bash
git checkout -b codex/vdl-studio-cli
```

Group commits into a single PR for the terminal release, but keep commits clean enough to review independently.

Recommended PR title:

```text
feat(studio): add interactive VDL Studio CLI
```

## Quality gates before merge

Before merging the terminal release:

- Existing command-line usage still works.
- `vdl` without args opens VDL Studio in TTY mode.
- `vdl --help` does not open the menu.
- Batch download queue records are written before processing.
- Automatic filenames match URL order.
- Cookie/token values are masked in summaries/logs.
- Interrupted batch can be resumed.
- Download concurrency is bounded by an explicit 1-4 job limit.
- Tests do not require private URLs, real cookies, OpenAI network access, or Whisper model downloads.
