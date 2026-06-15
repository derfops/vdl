# VDL Studio: strategy and assessment

## Purpose

VDL Studio is the planned evolution of the current `vdl` CLI into a personal workflow tool for managing video downloads, transcriptions, context files, subtitles, and generated artifacts.

This is not intended as a commercial product. The design target is a reliable personal operations tool with two usage modes:

- Interactive CLI first, for fast local usage without a web UI.
- Web UI later, backed by an API, queue, and workers.

The current `vdl` command should remain usable. VDL Studio should be added as an interactive layer and later as a service layer, not as a breaking rewrite.

## Current baseline

The repository already supports the core pipeline:

- Authenticated video download using `VDL_TOKEN` or cookie files.
- Local video processing.
- Audio extraction with `ffmpeg`.
- Local Whisper transcription.
- OpenAI API transcription/context generation.
- Subtitle generation and translation through `subtitles.py`.
- Docker execution with optional Gluetun/VPN routing.
- Basic logging and output directory organization.

The main limitation is not capability. The limitation is operational ergonomics: the user must remember flags, compose long commands, handle tokens manually, and infer which options are mutually exclusive.

## Strategic direction

VDL Studio should evolve in stages.

### Stage 1: Interactive CLI

The preferred entrypoint is:

```bash
vdl
```

When called without arguments, `vdl` should open VDL Studio in interactive mode.
Existing argument-based usage should remain available for scripts and advanced use.

An explicit alias may also be supported:

```bash
vdl studio
```

or:

```bash
vdl --studio
```

The command should open a guided menu and ask the user what to do.

Example top-level menu:

```text
VDL Studio

1. Download em lote
2. Gerar legendas
3. Gerar contexto
4. Consolidar em e-book
5. Sair
```

The CLI mode should support:

- Multiline URL input.
- Cookie/token input.
- Destination folder selection or manual path input.
- Processing preset selection.
- Validation of incompatible options before execution.
- A final review screen before starting.

### Target terminal flow

This is the required terminal experience for VDL Studio.

#### 1. Start command

The user runs:

```bash
vdl
```

If no arguments are passed, the system opens the interactive VDL Studio menu.

If arguments are passed, the current non-interactive CLI behavior remains available.

#### 2. Select operation

The system asks what the user wants to do:

```text
VDL Studio

O que deseja fazer?

1. Download em lote
2. Gerar legendas
3. Gerar contexto
4. Consolidar em e-book
5. Sair
```

Each option should trigger a guided flow with only the relevant prompts.

Cookie prompts are only required for `Download em lote`. The other operations should ask for an input path, output destination, and processing options relevant to the selected operation.

#### 3. Cookie input for download

For `Download em lote`, the system asks for the cookie/token.

The user may provide:

- Base64 `VDL_TOKEN`.
- Raw cookies JSON exported from the browser.
- Plain cookie header, such as `session=abc; other=def`.
- Existing cookie file path.
- Existing `VDL_TOKEN` from the environment.

The system must auto-detect the format and convert it internally to what the download pipeline expects.

Expected behavior:

```text
Autenticação de download

1. Usar VDL_TOKEN do ambiente
2. Colar cookie ou token agora
3. Ler arquivo de cookie
4. Prosseguir sem cookie
```

For option 2:

```text
Cole o cookie/token.
Aceito: Base64 VDL_TOKEN, cookies JSON puros ou header Cookie puro.
Finalize com uma linha contendo apenas END.
```

Detection rules:

- If the pasted value decodes as Base64 and produces valid JSON cookies, treat it as `VDL_TOKEN`.
- If the pasted value starts as JSON array/object, treat it as raw cookies and convert to Base64 internally when needed.
- If the pasted value looks like a plain cookie header, use the default browser user-agent.
- If the pasted value is a legacy plain token, process only if the existing parser still supports it.
- Never print the full cookie/token back to the terminal.
- Mask sensitive values in logs and summaries.

#### 4. Destination path

The system asks where all outputs should be saved:

```text
Destino dos arquivos:
> /data/cursos/arquitetura-cloud
```

Rules:

- The destination applies to all jobs in the batch.
- The system creates the directory if it does not exist, after confirmation.
- The system validates write permission before starting.
- Later, this can evolve into a terminal folder explorer, but manual path input is enough for the first implementation.

#### 5. Batch download and queue control

For `Download em lote`, the system asks for multiline URLs:

```text
Cole as URLs, uma por linha.
Finalize com uma linha contendo apenas END.

https://example.com/aula-01/playlist.m3u8
https://example.com/aula-02/playlist.m3u8
https://example.com/aula-03/playlist.m3u8
END
```

The system then creates a batch and writes a queue control file.

Suggested local state files:

```text
data/.vdl-studio/batches.jsonl
data/.vdl-studio/download_queue.jsonl
data/.vdl-studio/jobs.jsonl
```

Minimum queue record:

```json
{
  "batch_id": "batch_20260609_001",
  "job_id": "job_001",
  "position": 1,
  "url": "https://example.com/aula-01/playlist.m3u8",
  "output_filename": "01.mp4",
  "status": "queued",
  "stage": "download",
  "attempt": 0
}
```

The queue file is the source of truth for batch progress in CLI mode.

Rules:

- Jobs are created in the same order as the URLs.
- Jobs should default to sequential processing.
- Light parallelism can be offered later, but the first version should favor correctness.
- The user should be able to inspect the queue file if a process is interrupted.
- A resumed run should avoid re-downloading completed files unless explicitly requested.

#### 6. Automatic naming

For batch downloads, filenames are generated automatically from the URL order.

Default naming:

```text
01.mp4
02.mp4
03.mp4
...
NN.mp4
```

Rules:

- The first URL becomes `01.mp4`.
- The second URL becomes `02.mp4`.
- Numbers are zero-padded.
- Width starts at 2 digits and may grow when the batch size requires it.
- For 120 URLs, names should become `001.mp4` through `120.mp4`.
- Existing files should not be overwritten without confirmation.

Optional later extension:

```text
01-aula_cloud.mp4
02-aula_cloud.mp4
```

The default should remain order-based because it is predictable and does not depend on URL metadata.

### Stage 2: Job model and local queue

Introduce a consistent internal job model even before the web UI exists.

This allows the CLI and future API/frontend to use the same concepts:

- Batch
- Job
- Stage
- Artifact
- Credential
- Queue limit
- Retry
- Failure reason

The first implementation can run sequentially or with light local parallelism. It does not need Redis or a service API yet.

### Stage 3: VDL Studio API and frontend

Once the CLI flow is stable, add:

- FastAPI backend.
- Redis/RQ worker queue.
- SQLite initially, Postgres later if needed.
- React/Vite frontend.
- Server folder explorer.
- Job dashboard.
- Artifact library.

The frontend should call the API only. It should not know details about `yt-dlp`, Whisper, `ffmpeg`, or cookie conversion.

## Assessment: what needs improvement

### 1. CLI ergonomics

Current state:

- The CLI is flag-driven.
- It works for known flows, but it is easy to forget valid combinations.
- Mutually exclusive options are validated, but only after command composition.

Needed improvement:

- Add an interactive menu for common workflows.
- Present only valid next choices based on prior answers.
- Show a final summary before execution.

Recommended approach:

- Keep `argparse` for existing non-interactive usage.
- Add a separate interactive entrypoint.
- Use a Python CLI prompt library only if it remains lightweight and maintainable.

Candidate libraries:

- `questionary`: good UX, simple menus, checkboxes, confirmations.
- `InquirerPy`: similar, modern prompt support.
- `prompt_toolkit`: lower-level and powerful, useful for multiline input.
- Standard library fallback: acceptable but less ergonomic.

Recommendation:

- Use `questionary` or `InquirerPy` for menus.
- Use a custom multiline input helper if the chosen library does not handle pasted multi-line values cleanly.

### 2. Multiline input

The CLI should support pasting many URLs at once.

Proposed behavior:

```text
Cole as URLs, uma por linha.
Finalize com uma linha contendo apenas END.

https://example.com/aula-01/playlist.m3u8
https://example.com/aula-02/playlist.m3u8
https://example.com/aula-03/playlist.m3u8
END
```

Validation rules:

- Empty lines are ignored.
- Duplicate URLs are detected and shown.
- Invalid URL-looking lines are shown before execution.
- The user can continue, edit, or cancel.

Filename generation:

```text
Resultado:
- 01.mp4
- 02.mp4
- 03.mp4
```

The default should be order-based. A filename template may be added later:

```text
{index}
{index:03}
{slug}
```

### 3. Cookie and token input

Current state:

- `VDL_TOKEN` in Base64 is supported.
- Cookie JSON files are supported.
- Some legacy cookie formats are still handled.

Needed improvement:

- The interactive CLI should ask how the user wants to provide credentials.

Proposed menu:

```text
Como deseja autenticar o download?

1. Usar VDL_TOKEN existente no ambiente
2. Colar token Base64 agora
3. Colar cookies JSON agora
4. Ler arquivo de cookies
5. Prosseguir sem credencial
```

Proposed rules:

- If the user pastes cookies JSON, the CLI may convert to Base64 internally.
- If the user pastes Base64, the CLI should validate whether it decodes.
- The token should not be printed back in full.
- Logs must mask token/cookie values.
- The user should choose whether to save a named credential for later.

Credential saving for personal use:

```text
Salvar esta credencial como "hotmart-principal"? [s/N]
```

If saved, prefer a local config file outside source control, for example:

```text
data/.vdl-studio/credentials.json
```

or:

```text
~/.config/vdl-studio/credentials.json
```

For this repository, avoid committing any real credential material.

### 4. Option consistency

The current command validates incompatible flags, but the planned CLI and web UI need a clearer shared rule model.

Required rules:

- `only_download` cannot be combined with processing stages.
- Local mode does not require download credentials.
- Download mode requires URL and output filename.
- Context generation requires a transcription.
- Subtitle generation requires either an existing transcript or a transcription step.
- OpenAI-based transcription requires `OPENAI_API_KEY`.
- Local Whisper transcription enables `whisper_model` and `gpu`.
- OpenAI transcription disables local Whisper model and GPU options.
- If transcription is `none`, context options must be disabled.
- E-book consolidation requires existing `.md` context files.

Recommendation:

- Move option validation into a reusable validation module.
- Use the same validation module for:
  - `argparse` CLI
  - interactive CLI
  - future API
  - future frontend capabilities endpoint

### 5. Job control consistency

Job control is the most important area to make rigorous before introducing parallelism.

Recommended job states:

```text
queued
running
succeeded
failed
cancelled
blocked
```

Recommended stage names:

```text
validate_input
resolve_credentials
download
extract_audio
transcribe
generate_context
generate_subtitles
consolidate_contexts
finalize
```

Allowed actions by state:

| State | Allowed actions |
|---|---|
| `queued` | cancel, reorder |
| `running` | request cancel, view logs |
| `succeeded` | open artifacts, create derived job |
| `failed` | retry, view logs |
| `cancelled` | retry |
| `blocked` | fix configuration, retry |

Rules:

- A job should have exactly one current state.
- A job should expose current stage separately from state.
- Failures should store machine-readable reason codes.
- Logs should be linked to job IDs.
- Retries should create a new attempt, not overwrite previous attempt history.
- A batch should continue or stop based on explicit `stop_on_failure`.

### 6. Parallelism and limits

For personal use, the default should be conservative.

Recommended defaults:

```text
global_running_jobs = 2
download = 2
ffmpeg = 1
transcription_local = 1
openai = 1
subtitles = 1
```

Current CLI implementation:

- Download batches ask for a bounded 1-4 simultaneous job limit.
- Pending, failed, blocked, or interrupted download jobs can be resumed from the local JSONL state.
- Credentials are requested again during resume and are not persisted in queue state.

Interactive CLI should ask:

```text
Como executar o lote?

1. Sequencial
2. Paralelo leve
3. Personalizado
```

Parallelism should be bounded by stage type, not only by total job count.

Rationale:

- Downloads are mostly network I/O and can tolerate small parallelism.
- `ffmpeg` and local Whisper can saturate CPU/RAM/GPU.
- OpenAI calls should respect rate limits and cost control.

### 7. Artifact model

The current file outputs are useful, but VDL Studio needs a formal artifact registry.

Artifact types:

```text
video_mp4
audio_mp3
transcript_txt
context_md
subtitle_srt
ebook_md
log
```

Each artifact should track:

- Type
- Path
- Source job
- Created timestamp
- Whether it exists
- Whether it is stale relative to source input

This enables library actions such as:

- Generate context from existing transcript.
- Generate subtitles from existing video/audio.
- Reprocess transcription.
- Open artifact folder.
- Retry only failed stage.

### 8. Configuration

VDL Studio should distinguish between runtime options and persistent defaults.

Suggested config areas:

- OpenAI key status.
- Default transcription mode.
- Default Whisper model.
- Default device preference.
- Allowed output roots.
- Named download credentials.
- Queue limits.
- Filename template defaults.

Potential local config paths:

```text
data/.vdl-studio/config.json
data/.vdl-studio/credentials.json
data/.vdl-studio/jobs.jsonl
```

For a later service implementation, replace or mirror these with SQLite tables.

### 9. Observability

Current logs exist, but VDL Studio should make logs job-oriented.

Needed improvement:

- Include `batch_id`, `job_id`, `attempt`, and `stage` in logs.
- Mask sensitive values.
- Persist structured event records.
- Keep human-readable logs for debugging.

Minimal event format:

```json
{
  "ts": "2026-06-09T12:00:00-03:00",
  "batch_id": "batch_20260609_001",
  "job_id": "job_001",
  "attempt": 1,
  "stage": "download",
  "level": "info",
  "message": "Download started"
}
```

### 10. Code structure

The current code is functional, but VDL Studio will be easier if responsibilities are separated.

Recommended future modules:

```text
vdl/
  cli/
    argparse_cli.py
    studio_cli.py
    prompts.py
  core/
    models.py
    validation.py
    pipeline.py
    artifacts.py
    credentials.py
    config.py
  jobs/
    state.py
    runner.py
    events.py
  integrations/
    ytdlp.py
    ffmpeg.py
    whisper_local.py
    openai_api.py
  ui_api/
    app.py
    routes.py
```

This should be done incrementally. Do not rewrite everything before adding value.

## Proposed interactive CLI flow

### Create batch

```text
VDL Studio > Download em lote

1. Defina credencial
2. Escolha destino
3. Cole URLs
4. Escolha processamento
5. Escolha execução
6. Revisar e iniciar
```

### Processing menu

```text
Transcrição:

1. Nenhuma
2. Local Whisper
3. OpenAI
```

If `Local Whisper`:

```text
Modelo Whisper:
1. tiny
2. base
3. small
4. medium
5. large

Device:
1. CPU
2. GPU se disponível
```

If `OpenAI`:

```text
OpenAI API key encontrada? Sim
Modelo local/GPU: desabilitado
```

Derived outputs:

```text
Gerar contexto? [s/N]
Gerar legendas? [s/N]
Consolidar e-book ao final? [s/N]
```

The menu must prevent invalid combinations instead of only reporting them after selection.

### Final review

```text
Resumo do lote

URLs: 12
Destino: /data/cursos/arquitetura-cloud
Credencial: hotmart-principal
Arquivos: 01.mp4 ... 12.mp4
Transcrição: Local Whisper / base / CPU
Contexto: sim
Legendas: não
Execução: paralelo leve, max 2
Continuar após falha: sim

Iniciar? [s/N]
```

## Recommended implementation order

1. Document and freeze the VDL Studio concept.
2. Extract reusable validation rules from `main()`.
3. Define internal models for batch, job, stage, artifact, and credential.
4. Add interactive CLI for `Download em lote`.
5. Add multiline input and credential input handling.
6. Add job-oriented logs and run summary.
7. Add local job history file.
8. Add folder explorer behavior for CLI path selection.
9. Add API and queue only after CLI semantics are stable.
10. Add frontend using the Figma screens as product reference.

## Open decisions

These decisions should be made before implementation:

- Whether named credentials live under `data/.vdl-studio` or user config in `~/.config`.
- Whether interactive CLI should add a dependency such as `questionary`.
- Whether local job history starts as JSONL or SQLite.
- Whether downloaded URLs should be persisted in history.
- Whether cookie material should ever be persisted or only used per session.

## Immediate recommendation

Do not start with the web UI or microservices.

Start by making the CLI guided, consistent, and job-aware. This gives immediate value and creates the domain model that the later FastAPI/React version can reuse.
