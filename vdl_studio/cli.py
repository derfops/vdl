from __future__ import annotations

import os
import subprocess
import sys
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from .credentials import (
    AuthDetails,
    DEFAULT_USER_AGENT,
    resolve_auth_from_environment,
    resolve_auth_from_file,
    resolve_pasted_auth,
)
from .filenames import ordered_filenames
from .models import Artifact, Batch, Job, JobStage, JobState
from .state import Event, StudioStateStore


CookieExtractor = Callable[[str], tuple[str, str, str | None, list[dict] | None] | None]


@dataclass(frozen=True)
class StudioCallbacks:
    cookie_extractor: CookieExtractor
    download_video: Callable[[str, str, str, str, str | None, list[dict] | None], bool]
    extract_audio: Callable[[str, str, bool], str | None]
    transcribe_audio_local: Callable[[str, str, bool, str], str | None]
    transcribe_and_generate_context_via_api: Callable[[str, str, str], None]
    generate_context_from_text: Callable[[str, str, str], None]
    script_dir: str


def run_studio(callbacks: StudioCallbacks) -> int:
    if not sys.stdin.isatty():
        print("VDL Studio precisa de um terminal interativo. Use 'vdl --help' para o modo por argumentos.")
        return 2

    while True:
        choice = _menu(
            "VDL Studio\n\nO que deseja fazer?",
            [
                "Download em lote",
                "Retomar lote de download",
                "Gerar legendas",
                "Gerar contexto",
                "Consolidar em e-book",
                "Sair",
            ],
        )
        if choice == 1:
            _download_batch(callbacks)
        elif choice == 2:
            _resume_download_batch(callbacks)
        elif choice == 3:
            _generate_subtitles(callbacks)
        elif choice == 4:
            _generate_context(callbacks)
        elif choice == 5:
            _consolidate_ebook(callbacks)
        elif choice == 6:
            return 0


def _download_batch(callbacks: StudioCallbacks) -> None:
    auth = _prompt_auth(callbacks.cookie_extractor)
    destination = _prompt_destination()
    urls = _prompt_urls()
    if not urls:
        print("Nenhuma URL informada.")
        return

    filenames = ordered_filenames(len(urls))
    _report_existing_outputs(destination, filenames)
    max_workers = _prompt_worker_count()
    continue_after_failure = _confirm("Continuar lote apos falhas?", default=True)

    print("\nResumo do lote")
    print(f"URLs: {len(urls)}")
    print(f"Destino: {destination}")
    print(f"Credencial: {auth.masked_label() if auth else 'sem credencial'}")
    print(f"Arquivos: {filenames[0]} ... {filenames[-1]}")
    print(f"Execucao: {max_workers} job(s) simultaneo(s)")
    print(f"Continuar apos falha: {'sim' if continue_after_failure else 'nao'}")
    if not _confirm("Iniciar?", default=False):
        print("Cancelado.")
        return

    batch = _create_batch(destination, urls, filenames)
    state = StudioStateStore(_default_state_root())
    state.append_batch(batch)
    for job in batch.jobs:
        state.append_queued_job(job)

    _run_download_jobs(callbacks, state, batch, auth, continue_after_failure, max_workers)


def _resume_download_batch(callbacks: StudioCallbacks) -> None:
    state = StudioStateStore(_default_state_root())
    batch = _prompt_batch_to_resume(state)
    if not batch:
        return

    pending = _pending_download_jobs(batch)
    if not pending:
        print("Esse lote nao tem jobs pendentes.")
        return

    auth = _prompt_auth(callbacks.cookie_extractor)
    max_workers = _prompt_worker_count()
    continue_after_failure = _confirm("Continuar lote apos falhas?", default=True)

    print("\nResumo da retomada")
    print(f"Lote: {batch.batch_id}")
    print(f"Pendentes: {len(pending)} de {len(batch.jobs)}")
    print(f"Destino: {batch.destination}")
    print(f"Credencial: {auth.masked_label() if auth else 'sem credencial'}")
    print(f"Execucao: {max_workers} job(s) simultaneo(s)")
    if not _confirm("Retomar?", default=False):
        print("Cancelado.")
        return

    _run_download_jobs(callbacks, state, batch, auth, continue_after_failure, max_workers)


def _prompt_auth(extractor: CookieExtractor) -> AuthDetails | None:
    choice = _menu(
        "Autenticacao de download",
        [
            "Usar VDL_TOKEN do ambiente",
            "Colar cookie ou token agora",
            "Ler arquivo de cookie",
            "Prosseguir sem cookie",
        ],
    )
    if choice == 1:
        auth = resolve_auth_from_environment(os.environ, extractor)
        if auth:
            print("VDL_TOKEN detectado e validado.")
            return auth
        print("VDL_TOKEN ausente ou invalido.")
        return _prompt_auth(extractor)
    if choice == 2:
        raw = _multiline(
            "Cole o cookie/token.\nAceito: Base64 VDL_TOKEN, cookies JSON puros ou Cookie header.\nFinalize com END."
        )
        auth = resolve_pasted_auth(raw, extractor)
        if auth:
            print("Credencial detectada e validada.")
            return auth
        print("Nao consegui detectar um formato de credencial valido.")
        return _prompt_auth(extractor)
    if choice == 3:
        path = input("Caminho do arquivo de cookie: ").strip()
        try:
            auth = resolve_auth_from_file(path, extractor)
        except OSError as exc:
            print(f"Falha ao ler arquivo: {exc}")
            return _prompt_auth(extractor)
        if auth:
            print("Arquivo de cookie validado.")
            return auth
        print("Arquivo lido, mas formato nao reconhecido.")
        return _prompt_auth(extractor)
    return None


def _prompt_destination() -> str:
    while True:
        destination = input("Destino dos arquivos: ").strip() or "output_dir"
        path = Path(destination).expanduser()
        if not path.exists():
            if not _confirm(f"Criar diretorio {path}?", default=True):
                continue
            path.mkdir(parents=True, exist_ok=True)
        if not path.is_dir():
            print("O destino informado nao e um diretorio.")
            continue
        if not os.access(path, os.W_OK):
            print("O destino informado nao tem permissao de escrita.")
            continue
        return str(path)


def _prompt_urls() -> list[str]:
    raw = _multiline("Cole as URLs, uma por linha. Finalize com END.")
    urls = [line.strip() for line in raw.splitlines() if line.strip()]
    seen = set()
    duplicates = []
    unique_urls = []
    for url in urls:
        if url in seen:
            duplicates.append(url)
            continue
        seen.add(url)
        unique_urls.append(url)
    if duplicates:
        print(f"{len(duplicates)} URL(s) duplicada(s) ignorada(s).")
    suspicious = [url for url in unique_urls if not url.startswith(("http://", "https://"))]
    if suspicious:
        print("Linhas que nao parecem URLs HTTP(S):")
        for url in suspicious:
            print(f"- {url}")
        if not _confirm("Continuar mesmo assim?", default=False):
            return []
    return unique_urls


def _create_batch(destination: str, urls: list[str], filenames: list[str]) -> Batch:
    batch_id = f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
    jobs = [
        Job(
            batch_id=batch_id,
            job_id=f"job_{index:03d}",
            position=index,
            url=url,
            output_filename=filename,
        )
        for index, (url, filename) in enumerate(zip(urls, filenames), start=1)
    ]
    return Batch(batch_id=batch_id, destination=destination, jobs=jobs)


def _prompt_batch_to_resume(state: StudioStateStore) -> Batch | None:
    batches = [state.latest_batch_jobs(batch) for batch in state.list_batches()]
    incomplete = [batch for batch in batches if _pending_download_jobs(batch)]
    if not incomplete:
        print("Nenhum lote pendente encontrado.")
        return None

    print("\nLotes pendentes\n")
    for index, batch in enumerate(incomplete, start=1):
        pending = len(_pending_download_jobs(batch))
        print(f"{index}. {batch.batch_id} - {pending}/{len(batch.jobs)} pendente(s) - {batch.destination}")
    print(f"{len(incomplete) + 1}. Cancelar")

    while True:
        answer = input("> ").strip()
        if answer.isdigit():
            choice = int(answer)
            if 1 <= choice <= len(incomplete):
                return incomplete[choice - 1]
            if choice == len(incomplete) + 1:
                return None
        print("Opcao invalida.")


def _pending_download_jobs(batch: Batch) -> list[Job]:
    pending_states = {JobState.QUEUED, JobState.RUNNING, JobState.FAILED, JobState.BLOCKED}
    return [job for job in batch.jobs if job.status in pending_states]


def _run_download_jobs(
    callbacks: StudioCallbacks,
    state: StudioStateStore,
    batch: Batch,
    auth: AuthDetails | None,
    continue_after_failure: bool,
    max_workers: int,
) -> None:
    user_agent = auth.user_agent if auth else DEFAULT_USER_AGENT
    cookie_header = auth.cookie_header if auth else ""
    referer = auth.referer if auth else None
    cookies_list = auth.cookies_list if auth else None
    pending = _pending_download_jobs(batch)
    if not pending:
        print("Nenhum job pendente para processar.")
        return

    def worker(job: Job) -> Job:
        return _run_single_download_job(
            callbacks,
            state,
            batch,
            job,
            user_agent,
            cookie_header,
            referer,
            cookies_list,
        )

    if max_workers <= 1:
        for job in pending:
            finished = worker(job)
            if finished.status == JobState.FAILED and not continue_after_failure:
                print("Lote interrompido apos falha.")
                break
        return

    remaining = iter(pending)
    active: dict[Future[Job], Job] = {}
    should_stop_scheduling = False
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for _ in range(max_workers):
            job = next(remaining, None)
            if job is None:
                break
            active[executor.submit(worker, job)] = job

        while active:
            done, _ = wait(active.keys(), return_when=FIRST_COMPLETED)
            for future in done:
                active.pop(future)
                finished = future.result()
                if finished.status == JobState.FAILED and not continue_after_failure:
                    should_stop_scheduling = True
                    continue
                if should_stop_scheduling:
                    continue
                next_job = next(remaining, None)
                if next_job is not None:
                    active[executor.submit(worker, next_job)] = next_job
            if should_stop_scheduling and not active:
                print("Lote interrompido apos falha.")


def _run_single_download_job(
    callbacks: StudioCallbacks,
    state: StudioStateStore,
    batch: Batch,
    job: Job,
    user_agent: str,
    cookie_header: str,
    referer: str | None,
    cookies_list: list[dict] | None,
) -> Job:
    output_path = str(Path(batch.destination) / job.output_filename)
    if Path(output_path).exists():
        skipped = job.transition(
            status=JobState.SUCCEEDED,
            stage=JobStage.FINALIZE,
            artifacts=[Artifact(type="video_mp4", path=output_path, exists=True)],
        )
        state.append_job(skipped)
        state.append_event(_event(skipped, "info", "Arquivo ja existia; job marcado como concluido."))
        print(f"[{job.position}/{len(batch.jobs)}] Ja existe: {output_path}")
        return skipped

    running = state.transition(
        job,
        status=JobState.RUNNING,
        stage=JobStage.DOWNLOAD,
        increment_attempt=True,
    )
    state.append_event(_event(running, "info", "Download iniciado."))
    print(f"[{job.position}/{len(batch.jobs)}] Baixando {job.output_filename}")
    error = "download_failed"
    try:
        ok = callbacks.download_video(
            running.url,
            output_path,
            user_agent,
            cookie_header,
            referer,
            cookies_list,
        )
    except Exception as exc:
        ok = False
        error = f"{type(exc).__name__}: {exc}"
    if ok:
        succeeded = running.transition(
            status=JobState.SUCCEEDED,
            stage=JobStage.FINALIZE,
            artifacts=[Artifact(type="video_mp4", path=output_path, exists=True)],
        )
        state.append_job(succeeded)
        state.append_event(_event(succeeded, "info", "Download concluido."))
        return succeeded

    failed = running.transition(
        status=JobState.FAILED,
        stage=JobStage.DOWNLOAD,
        error=error,
    )
    state.append_job(failed)
    state.append_event(_event(failed, "error", "Download falhou."))
    return failed


def _prompt_worker_count() -> int:
    while True:
        answer = input("Jobs simultaneos [1, max 4]: ").strip()
        if not answer:
            return 1
        if not answer.isdigit():
            print("Informe um numero entre 1 e 4.")
            continue
        value = int(answer)
        if 1 <= value <= 4:
            return value
        print("Informe um numero entre 1 e 4.")


def _generate_subtitles(callbacks: StudioCallbacks) -> None:
    target = input("Arquivo ou diretorio de midia: ").strip()
    if not target:
        print("Caminho obrigatorio.")
        return
    if not Path(target).expanduser().exists():
        print("Arquivo ou diretorio nao encontrado.")
        return
    destination = _prompt_destination()
    model = input("Modelo Whisper [tiny]: ").strip() or "tiny"
    lang = input("Idioma alvo [pt-BR]: ").strip() or "pt-BR"
    engine = _menu("Traducao", ["openai", "none"])
    engine_value = "openai" if engine == 1 else "none"
    script = str(Path(callbacks.script_dir) / "subtitles.py")
    subprocess.run(
        [
            sys.executable,
            script,
            target,
            "--model",
            model,
            "--lang",
            lang,
            "--translate-engine",
            engine_value,
            "--output-dir",
            destination,
        ],
        check=False,
    )


def _generate_context(callbacks: StudioCallbacks) -> None:
    transcript_path = input("Arquivo de transcricao (.txt): ").strip()
    if not transcript_path:
        print("Arquivo obrigatorio.")
        return
    path = Path(transcript_path).expanduser()
    if not path.exists():
        print("Arquivo nao encontrado.")
        return
    destination = _prompt_destination()
    text = path.read_text(encoding="utf-8")
    callbacks.generate_context_from_text(text, str(path), destination)


def _consolidate_ebook(callbacks: StudioCallbacks) -> None:
    directory = input("Diretorio com contextos .md: ").strip() or "."
    script = str(Path(callbacks.script_dir) / "vdl.py")
    subprocess.run(
        [sys.executable, script, "--all-contexts", "-d", directory],
        check=False,
    )


def _menu(title: str, options: list[str]) -> int:
    while True:
        print(f"\n{title}\n")
        for index, option in enumerate(options, start=1):
            print(f"{index}. {option}")
        answer = input("> ").strip()
        if answer.isdigit() and 1 <= int(answer) <= len(options):
            return int(answer)
        print("Opcao invalida.")


def _multiline(prompt: str) -> str:
    print(f"\n{prompt}")
    lines = []
    while True:
        line = input()
        if line.strip() == "END":
            break
        lines.append(line)
    return "\n".join(lines)


def _confirm(prompt: str, default: bool) -> bool:
    suffix = "[S/n]" if default else "[s/N]"
    answer = input(f"{prompt} {suffix} ").strip().lower()
    if not answer:
        return default
    return answer in {"s", "sim", "y", "yes"}


def _report_existing_outputs(destination: str, filenames: list[str]) -> None:
    existing = [name for name in filenames if (Path(destination) / name).exists()]
    if not existing:
        return
    print("Arquivos existentes detectados:")
    for name in existing[:10]:
        print(f"- {name}")
    if len(existing) > 10:
        print(f"... e mais {len(existing) - 10}")


def _default_state_root() -> Path:
    cwd = Path.cwd()
    if cwd.name == "data":
        return cwd / ".vdl-studio"
    return cwd / "data" / ".vdl-studio"


def _event(job: Job, level: str, message: str) -> Event:
    return Event(
        batch_id=job.batch_id,
        job_id=job.job_id,
        attempt=job.attempt,
        stage=job.stage.value,
        level=level,
        message=message,
    )
