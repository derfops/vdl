from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal


RuntimeMode = Literal["none", "cyberghost", "windscribe"]
ProcessingMode = Literal["download", "transcribe", "context", "unified"]
LocalProcessingMode = Literal["transcribe", "context", "unified"]

LOCAL_MEDIA_EXTENSIONS = {".mp4", ".mkv", ".mov", ".webm", ".m4v"}
WHISPER_MODELS = {"tiny", "base", "small", "medium", "large"}


@dataclass(frozen=True)
class CommandResult:
    command: list[str]
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "returncode": self.returncode,
            "stdout": self.stdout[-8000:],
            "stderr": self.stderr[-8000:],
        }


@dataclass(frozen=True)
class RuntimeDefinition:
    mode: RuntimeMode
    label: str
    worker: str
    vpn: str | None
    up_command: str
    down_command: str
    rebuild_command: str
    logs_container: str


RUNTIMES: dict[RuntimeMode, RuntimeDefinition] = {
    "none": RuntimeDefinition(
        mode="none",
        label="Sem VPN",
        worker="vdl-novpn",
        vpn=None,
        up_command="up-novpn",
        down_command="down-novpn",
        rebuild_command="rebuild-novpn",
        logs_container="vdl-novpn",
    ),
    "cyberghost": RuntimeDefinition(
        mode="cyberghost",
        label="CyberGhost",
        worker="vdl",
        vpn="gluetun",
        up_command="up",
        down_command="down",
        rebuild_command="rebuild",
        logs_container="gluetun",
    ),
    "windscribe": RuntimeDefinition(
        mode="windscribe",
        label="Windscribe",
        worker="vdl-windscribe",
        vpn="gluetun-windscribe",
        up_command="up-windscribe",
        down_command="down-windscribe",
        rebuild_command="rebuild-windscribe",
        logs_container="gluetun-windscribe",
    ),
}

SENSITIVE_FILE_NAMES = {
    ".env",
    "cookie.txt",
    "cookies.json",
    "cookie.json",
    "token.txt",
    "vdl_token.env",
}


def now_iso() -> str:
    # Hora local do servidor (tz-aware), no MESMO fuso usado para gerar o batch_id.
    # Antes era UTC, o que divergia do batch_id (local) e confundia diagnósticos.
    return datetime.now().astimezone().isoformat()


class SafeRunner:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.script = self.project_root / "vdl.sh"

    def vdl_script(self, command: str, *args: str, timeout: int = 900) -> CommandResult:
        return self.run(["bash", str(self.script), command, *args], timeout=timeout)

    def docker(self, *args: str, timeout: int = 60, env: dict[str, str] | None = None) -> CommandResult:
        return self.run(["docker", *args], timeout=timeout, env=env)

    def run(
        self,
        command: list[str],
        timeout: int = 60,
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        proc_env = os.environ.copy()
        proc_env["VDL_PROJECT_ROOT"] = str(self.project_root)
        if env:
            proc_env.update(env)

        process = subprocess.run(
            command,
            cwd=self.project_root,
            env=proc_env,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        return CommandResult(command, process.returncode, process.stdout, process.stderr)


class RuntimeOrchestrator:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.runner = SafeRunner(project_root)

    def start(self, mode: RuntimeMode, rebuild: bool = False) -> dict[str, Any]:
        runtime = RUNTIMES[mode]
        command = runtime.rebuild_command if rebuild else runtime.up_command
        result = self.runner.vdl_script(command, timeout=1800)
        return {"mode": mode, "runtime": runtime.label, "result": result.to_dict()}

    def stop(self, mode: RuntimeMode) -> dict[str, Any]:
        runtime = RUNTIMES[mode]
        result = self.runner.vdl_script(runtime.down_command, timeout=600)
        return {"mode": mode, "runtime": runtime.label, "result": result.to_dict()}

    def status(self) -> dict[str, Any]:
        return {
            "runtimes": [self.runtime_status(mode) for mode in RUNTIMES],
            "updated_at": now_iso(),
        }

    def runtime_status(self, mode: RuntimeMode) -> dict[str, Any]:
        runtime = RUNTIMES[mode]
        worker = self.container_status(runtime.worker)
        vpn = self.container_status(runtime.vpn) if runtime.vpn else None
        running = worker.get("running", False)
        ready = running and (vpn is None or vpn.get("healthy", False) or vpn.get("running", False))
        return {
            "mode": runtime.mode,
            "label": runtime.label,
            "worker": worker,
            "vpn": vpn,
            "running": running,
            "ready": ready,
        }

    def container_status(self, name: str | None) -> dict[str, Any]:
        if not name:
            return {"name": None, "exists": False, "running": False, "healthy": False}
        result = self.runner.docker("inspect", name, timeout=20)
        if not result.ok:
            return {"name": name, "exists": False, "running": False, "healthy": False}
        data = json.loads(result.stdout)[0]
        state = data.get("State", {})
        health = state.get("Health", {})
        health_status = health.get("Status")
        return {
            "name": name,
            "exists": True,
            "running": bool(state.get("Running")),
            "status": state.get("Status"),
            "health": health_status,
            "healthy": health_status == "healthy",
            "started_at": state.get("StartedAt"),
        }

    def public_ip(self, mode: RuntimeMode) -> dict[str, Any]:
        runtime = RUNTIMES[mode]
        status = self.container_status(runtime.worker)
        if not status.get("running"):
            return {"mode": mode, "ok": False, "ip": None, "error": "worker nao esta rodando"}

        result = self.runner.docker(
            "exec",
            runtime.worker,
            "sh",
            "-lc",
            "curl -fsS --max-time 12 ifconfig.me",
            timeout=20,
        )
        return {
            "mode": mode,
            "ok": result.ok,
            "ip": result.stdout.strip() if result.ok else None,
            "error": result.stderr.strip() if not result.ok else None,
        }

    def logs(self, mode: RuntimeMode, tail: int = 160) -> dict[str, Any]:
        runtime = RUNTIMES[mode]
        tail = max(20, min(tail, 1000))
        result = self.runner.docker("logs", runtime.logs_container, "--tail", str(tail), timeout=30)
        return {"mode": mode, "container": runtime.logs_container, "result": result.to_dict()}


class FileExplorer:
    def __init__(self, data_root: Path) -> None:
        self.data_root = data_root.resolve()
        self.data_root.mkdir(parents=True, exist_ok=True)

    def list_path(self, container_path: str) -> dict[str, Any]:
        path = self._resolve(container_path)
        if not path.exists():
            raise FileNotFoundError(container_path)
        if not path.is_dir():
            raise NotADirectoryError(container_path)

        entries = []
        for item in sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
            if item.name.startswith(".") or item.name in SENSITIVE_FILE_NAMES:
                continue
            entries.append(
                {
                    "name": item.name,
                    "path": self._to_container_path(item),
                    "type": "directory" if item.is_dir() else "file",
                    "size": item.stat().st_size if item.is_file() else None,
                }
            )
        return {"path": self._to_container_path(path), "entries": entries}

    def create_directory(self, container_path: str) -> dict[str, Any]:
        path = self._resolve(container_path)
        path.mkdir(parents=True, exist_ok=True)
        return {"path": self._to_container_path(path), "created": True}

    def resolve_preview_file(self, container_path: str) -> Path:
        path = self._resolve(container_path)
        if not path.exists():
            raise FileNotFoundError(container_path)
        if not path.is_file():
            raise IsADirectoryError(container_path)
        relative_parts = path.relative_to(self.data_root).parts
        if any(part.startswith(".") or part in SENSITIVE_FILE_NAMES for part in relative_parts):
            raise ValueError("Arquivo protegido nao pode ser pre-visualizado.")
        return path

    def _resolve(self, container_path: str) -> Path:
        clean = container_path.strip() or "/data"
        if clean == "/data":
            return self.data_root
        if not clean.startswith("/data/"):
            raise ValueError("Somente caminhos dentro de /data sao permitidos.")
        relative = clean.removeprefix("/data/").strip("/")
        path = (self.data_root / relative).resolve()
        if self.data_root != path and self.data_root not in path.parents:
            raise ValueError("Caminho fora de /data.")
        return path

    def _to_container_path(self, path: Path) -> str:
        resolved = path.resolve()
        if resolved == self.data_root:
            return "/data"
        return "/data/" + str(resolved.relative_to(self.data_root)).replace(os.sep, "/")


@dataclass
class JobRecord:
    job_id: str
    batch_id: str
    mode: RuntimeMode
    position: int
    url: str
    filename: str
    destination: str
    processing_mode: ProcessingMode
    job_type: str = "download"
    input_path: str | None = None
    options: dict[str, Any] = field(default_factory=dict)
    status: str = "queued"
    stage: str = "queued"
    attempt: int = 0
    logs: str = ""
    error: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    updated_at: str = field(default_factory=now_iso)

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class BatchRecord:
    batch_id: str
    mode: RuntimeMode
    destination: str
    processing_mode: ProcessingMode
    concurrency: int
    created_at: str
    jobs: list[JobRecord]
    job_type: str = "download"
    source_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = self.__dict__.copy()
        data["jobs"] = [job.to_dict() for job in self.jobs]
        return data


class JobManager:
    def __init__(
        self,
        data_root: Path,
        orchestrator: RuntimeOrchestrator,
    ) -> None:
        self.data_root = data_root
        self.state_dir = Path(os.getenv("VDL_STUDIO_STATE_DIR", data_root / ".vdl-studio-web"))
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.state_dir / "jobs.json"
        self.orchestrator = orchestrator
        self._lock = threading.Lock()
        self._batches: dict[str, BatchRecord] = {}
        self._cancelled_batches: set[str] = set()
        self._cancelled_jobs: set[tuple[str, str]] = set()
        self._load()

    def create_download_batch(
        self,
        mode: RuntimeMode,
        urls: list[str],
        destination: str,
        cookie: str | None,
        concurrency: int,
        processing_mode: ProcessingMode,
        filenames: list[str] | None = None,
    ) -> dict[str, Any]:
        clean_urls = [url.strip() for url in urls if url.strip()]
        if not clean_urls:
            raise ValueError("Informe ao menos uma URL.")
        invalid = [url for url in clean_urls if not re.match(r"^https?://", url)]
        if invalid:
            raise ValueError(f"URLs invalidas: {', '.join(invalid[:3])}")
        if not (cookie or "").strip():
            raise ValueError("Cookie obrigatorio para downloads via VDL Studio.")

        # Nomes finais: 1 por URL (posicional). Vazio -> numero sequencial 01-NN.
        output_names = build_download_filenames(clean_urls, filenames)

        self._ensure_runtime_ready(mode)

        concurrency = max(1, min(concurrency, 4))
        destination = normalize_data_destination(destination)
        width = max(2, len(str(len(clean_urls))))
        batch_id = f"batch-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
        jobs = [
            JobRecord(
                job_id=f"job-{index:0{width}d}",
                batch_id=batch_id,
                mode=mode,
                position=index,
                url=url,
                filename=output_names[index - 1],
                destination=destination,
                processing_mode=processing_mode,
            )
            for index, url in enumerate(clean_urls, start=1)
        ]
        batch = BatchRecord(
            batch_id=batch_id,
            mode=mode,
            destination=destination,
            processing_mode=processing_mode,
            concurrency=concurrency,
            created_at=now_iso(),
            jobs=jobs,
        )
        with self._lock:
            self._batches[batch_id] = batch
            self._save_locked()

        token = normalize_cookie_to_vdl_token(cookie)
        thread = threading.Thread(
            target=self._run_batch,
            args=(batch_id, token),
            daemon=True,
            name=f"vdl-studio-{batch_id}",
        )
        thread.start()
        return batch.to_dict()

    def create_local_transcription_batch(
        self,
        mode: RuntimeMode,
        source_path: str,
        destination: str | None,
        concurrency: int,
        processing_mode: LocalProcessingMode,
        use_gpu: bool,
        whisper_model: str,
    ) -> dict[str, Any]:
        if whisper_model not in WHISPER_MODELS:
            raise ValueError("Modelo Whisper invalido.")
        source_path = normalize_data_container_path(source_path)
        destination = normalize_data_destination(destination or default_destination_for_source(self.data_root, source_path))
        media_files = list_local_media_files(self.data_root, source_path)

        self._ensure_runtime_ready(mode)

        concurrency = max(1, min(concurrency, 2))
        width = max(2, len(str(len(media_files))))
        batch_id = f"batch-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
        jobs = [
            JobRecord(
                job_id=f"job-{index:0{width}d}",
                batch_id=batch_id,
                mode=mode,
                position=index,
                url=item["path"],
                input_path=item["path"],
                filename=item["name"],
                destination=destination,
                processing_mode=processing_mode,
                job_type="local",
                options={"use_gpu": use_gpu, "whisper_model": whisper_model},
            )
            for index, item in enumerate(media_files, start=1)
        ]
        batch = BatchRecord(
            batch_id=batch_id,
            mode=mode,
            destination=destination,
            processing_mode=processing_mode,
            concurrency=concurrency,
            created_at=now_iso(),
            jobs=jobs,
            job_type="local",
            source_path=source_path,
        )
        with self._lock:
            self._batches[batch_id] = batch
            self._save_locked()

        thread = threading.Thread(
            target=self._run_batch,
            args=(batch_id, None),
            daemon=True,
            name=f"vdl-studio-{batch_id}",
        )
        thread.start()
        return batch.to_dict()

    def list_batches(self) -> dict[str, Any]:
        with self._lock:
            batches = sorted(self._batches.values(), key=lambda b: b.created_at, reverse=True)
            return {"batches": [batch.to_dict() for batch in batches], "server_now": now_iso()}

    def _ensure_runtime_ready(self, mode: RuntimeMode) -> None:
        """Valida que o runtime esta pronto ANTES de criar/reprocessar um lote.

        Sem isso o lote era criado e todos os jobs caiam em 'blocked', sem como limpar.
        """
        status = self.orchestrator.runtime_status(mode)
        if status.get("ready"):
            return
        runtime = RUNTIMES[mode]
        worker = status.get("worker") or {}
        if not worker.get("running"):
            raise ValueError(
                f"O runtime {runtime.label} nao esta iniciado. Inicie o runtime antes de criar o lote."
            )
        raise ValueError(
            f"O runtime {runtime.label} ainda nao esta pronto (VPN nao saudavel). Aguarde ficar pronto e tente de novo."
        )

    def _run_batch(self, batch_id: str, token: str | None) -> None:
        with self._lock:
            batch = self._batches.get(batch_id)
            if batch is None:
                return
            mode = batch.mode
            concurrency = batch.concurrency
            # Apenas jobs pendentes: permite reprocessar um lote sem refazer os ja concluidos.
            jobs = [job for job in batch.jobs if job.status == "queued"]

        if not jobs:
            return

        runtime_status = self.orchestrator.runtime_status(mode)
        if not runtime_status.get("ready"):
            for job in jobs:
                self._transition(job.batch_id, job.job_id, "blocked", "runtime", "Runtime nao esta pronto.")
            return

        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = [executor.submit(self._run_job, job, token) for job in jobs]
            for future in as_completed(futures):
                future.result()

    def _run_job(self, job: JobRecord, token: str | None) -> None:
        if self._is_cancelled(job.batch_id, job.job_id):
            self._transition(job.batch_id, job.job_id, "canceled", "canceled", "Cancelado antes de iniciar.", finished=True)
            return

        if job.job_type == "local":
            self._run_local_job(job)
            return

        runtime = RUNTIMES[job.mode]
        self._transition(job.batch_id, job.job_id, "running", "vdl", None, started=True)

        args = [
            "exec",
        ]
        if token:
            args.extend(["-e", f"VDL_TOKEN={token}"])
        args.extend(
            [
                runtime.worker,
                "vdl",
                job.url,
                job.filename,
                "-d",
                job.destination,
                *processing_args(job.processing_mode),
            ]
        )

        result = self.orchestrator.runner.docker(*args, timeout=24 * 60 * 60)
        logs = "\n".join(part for part in [result.stdout, result.stderr] if part).strip()
        if self._is_cancelled(job.batch_id, job.job_id):
            self._transition(job.batch_id, job.job_id, "canceled", "canceled", "Cancelado pelo usuario.", logs=logs, finished=True)
        elif result.ok:
            self._transition(job.batch_id, job.job_id, "succeeded", "finished", None, logs=logs, finished=True)
        else:
            self._transition(job.batch_id, job.job_id, "failed", "vdl", result.stderr[-2000:] or "Falha no VDL.", logs=logs, finished=True)

    def _run_local_job(self, job: JobRecord) -> None:
        runtime = RUNTIMES[job.mode]
        input_path = job.input_path or job.url
        self._transition(job.batch_id, job.job_id, "running", "transcribe", None, started=True)

        args = [
            "exec",
            runtime.worker,
            "vdl",
            input_path,
            "--local",
            "-d",
            job.destination,
            *local_processing_args(job.processing_mode),
        ]
        # OpenAI (unified) envia o audio para a API: whisper local/GPU nao se aplicam
        # e o vdl.py rejeita a combinacao.
        if job.processing_mode != "unified":
            whisper_model = str(job.options.get("whisper_model") or "base")
            if whisper_model != "base":
                args.extend(["--whisper-model", whisper_model])
            if bool(job.options.get("use_gpu")):
                args.append("--gpu")

        result = self.orchestrator.runner.docker(*args, timeout=24 * 60 * 60)
        logs = "\n".join(part for part in [result.stdout, result.stderr] if part).strip()
        if self._is_cancelled(job.batch_id, job.job_id):
            self._transition(job.batch_id, job.job_id, "canceled", "canceled", "Cancelado pelo usuario.", logs=logs, finished=True)
        elif result.ok:
            self._transition(job.batch_id, job.job_id, "succeeded", "finished", None, logs=logs, finished=True)
        else:
            self._transition(job.batch_id, job.job_id, "failed", "transcribe", result.stderr[-2000:] or "Falha no VDL.", logs=logs, finished=True)

    def _transition(
        self,
        batch_id: str,
        job_id: str,
        status: str,
        stage: str,
        error: str | None,
        logs: str | None = None,
        started: bool = False,
        finished: bool = False,
    ) -> None:
        with self._lock:
            job = self._find_job_locked(batch_id, job_id)
            if job is None:
                # Lote pode ter sido excluido enquanto o job rodava: ignora em silencio.
                return
            job.status = status
            job.stage = stage
            job.error = error
            job.updated_at = now_iso()
            if started:
                job.started_at = job.started_at or job.updated_at
                job.attempt += 1
            if finished:
                job.finished_at = job.updated_at
            if logs:
                job.logs = logs[-12000:]
            self._save_locked()

    def _find_job_locked(self, batch_id: str, job_id: str) -> JobRecord | None:
        batch = self._batches.get(batch_id)
        if batch is None:
            return None
        for job in batch.jobs:
            if job.job_id == job_id:
                return job
        return None

    def _is_cancelled(self, batch_id: str, job_id: str) -> bool:
        with self._lock:
            return batch_id in self._cancelled_batches or (batch_id, job_id) in self._cancelled_jobs

    def _terminate_in_container(self, mode: RuntimeMode, marker: str | None) -> None:
        """Mata, em best-effort, o processo vdl correspondente dentro do worker.

        O job roda como `vdl <marker> ...` dentro do container, entao pkill -f <marker>
        encerra o download em andamento. Se nada casar, o job ainda sera marcado como
        cancelado quando o docker exec retornar.
        """
        if not marker:
            return
        runtime = RUNTIMES[mode]
        try:
            self.orchestrator.runner.docker("exec", runtime.worker, "pkill", "-f", marker, timeout=20)
        except Exception:
            pass

    def delete_batch(self, batch_id: str, force: bool = False) -> dict[str, Any]:
        with self._lock:
            batch = self._batches.get(batch_id)
            if batch is None:
                raise KeyError(batch_id)
            running = [job for job in batch.jobs if job.status == "running"]
            if running and not force:
                raise ValueError(
                    f"Lote possui {len(running)} job(s) em execucao. Cancele o lote antes de excluir."
                )
            del self._batches[batch_id]
            self._cancelled_batches.discard(batch_id)
            self._cancelled_jobs = {pair for pair in self._cancelled_jobs if pair[0] != batch_id}
            self._save_locked()
        return {"batch_id": batch_id, "deleted": True}

    def cancel_batch(self, batch_id: str) -> dict[str, Any]:
        with self._lock:
            batch = self._batches.get(batch_id)
            if batch is None:
                raise KeyError(batch_id)
            self._cancelled_batches.add(batch_id)
            mode = batch.mode
            cancelled = 0
            running: list[tuple[str, str]] = []
            for job in batch.jobs:
                if job.status == "queued":
                    job.status = "canceled"
                    job.stage = "canceled"
                    job.error = "Cancelado pelo usuario."
                    job.updated_at = now_iso()
                    job.finished_at = job.updated_at
                    self._cancelled_jobs.add((batch_id, job.job_id))
                    cancelled += 1
                elif job.status == "running":
                    self._cancelled_jobs.add((batch_id, job.job_id))
                    marker = (job.input_path or job.url) if job.job_type == "local" else job.url
                    running.append((job.job_id, marker))
                    cancelled += 1
            self._save_locked()

        # Encerra os jobs em execucao fora do lock (chamada ao docker pode demorar).
        for _job_id, marker in running:
            self._terminate_in_container(mode, marker)
        return {"batch_id": batch_id, "canceled": cancelled, "running_signaled": len(running)}

    def retry_batch(self, batch_id: str, cookie: str | None = None) -> dict[str, Any]:
        with self._lock:
            batch = self._batches.get(batch_id)
            if batch is None:
                raise KeyError(batch_id)
            mode = batch.mode
            job_type = batch.job_type
            retryable = [job for job in batch.jobs if job.status in ("blocked", "failed", "canceled", "interrupted")]
            if not retryable:
                raise ValueError("Nenhum job para reprocessar (somente bloqueados, falhos, cancelados ou interrompidos).")

        # Valida o runtime antes de reabrir os jobs, para nao recair em 'blocked'.
        self._ensure_runtime_ready(mode)

        token = None
        if job_type == "download":
            if not (cookie or "").strip():
                raise ValueError("Cookie obrigatorio para reprocessar um lote de download.")
            token = normalize_cookie_to_vdl_token(cookie)

        with self._lock:
            batch = self._batches.get(batch_id)
            if batch is None:
                raise KeyError(batch_id)
            self._cancelled_batches.discard(batch_id)
            reopened = 0
            for job in batch.jobs:
                if job.status in ("blocked", "failed", "canceled", "interrupted"):
                    self._cancelled_jobs.discard((batch_id, job.job_id))
                    job.status = "queued"
                    job.stage = "queued"
                    job.error = None
                    job.started_at = None
                    job.finished_at = None
                    job.updated_at = now_iso()
                    reopened += 1
            self._save_locked()
            snapshot = batch.to_dict()

        thread = threading.Thread(
            target=self._run_batch,
            args=(batch_id, token),
            daemon=True,
            name=f"vdl-studio-{batch_id}-retry",
        )
        thread.start()
        snapshot["reopened"] = reopened
        return snapshot

    def rename_job(self, batch_id: str, job_id: str, new_name: str) -> dict[str, Any]:
        """Renomeia o arquivo de saida de um job concluido no disco e no registro."""
        new_filename = sanitize_output_filename(new_name)
        with self._lock:
            batch = self._batches.get(batch_id)
            if batch is None:
                raise KeyError(batch_id)
            job = next((item for item in batch.jobs if item.job_id == job_id), None)
            if job is None:
                raise KeyError(job_id)
            if job.job_type != "download":
                raise ValueError("Renomeacao disponivel apenas para jobs de download.")
            if job.status != "succeeded":
                raise ValueError("So e possivel renomear o arquivo de um job concluido.")
            old_filename = job.filename
            destination = job.destination
            if any(item is not job and item.filename == new_filename for item in batch.jobs):
                raise ValueError(f"Ja existe um job neste lote com o nome {new_filename}.")

        if new_filename == old_filename:
            return {"batch_id": batch_id, "job_id": job_id, "filename": new_filename, "old_filename": old_filename}

        dest_dir = resolve_data_path(self.data_root, destination)
        old_path = dest_dir / old_filename
        new_path = dest_dir / new_filename
        if not old_path.exists():
            raise ValueError(f"Arquivo nao encontrado: {destination}/{old_filename}")
        if new_path.exists():
            raise ValueError(f"Ja existe um arquivo chamado {new_filename} no destino.")
        old_path.rename(new_path)

        with self._lock:
            job = self._find_job_locked(batch_id, job_id)
            if job is not None:
                job.filename = new_filename
                job.updated_at = now_iso()
                self._save_locked()
        return {"batch_id": batch_id, "job_id": job_id, "filename": new_filename, "old_filename": old_filename}

    def _load(self) -> None:
        if not self.state_file.exists():
            return
        data = json.loads(self.state_file.read_text(encoding="utf-8"))
        for batch_data in data.get("batches", []):
            jobs = [JobRecord(**job) for job in batch_data.get("jobs", [])]
            batch = BatchRecord(
                batch_id=batch_data["batch_id"],
                mode=batch_data["mode"],
                destination=batch_data["destination"],
                processing_mode=batch_data.get("processing_mode", "download"),
                concurrency=batch_data.get("concurrency", 1),
                created_at=batch_data["created_at"],
                jobs=jobs,
                job_type=batch_data.get("job_type", "download"),
                source_path=batch_data.get("source_path"),
            )
            self._batches[batch.batch_id] = batch
        self._reconcile_orphans_on_load()

    def _reconcile_orphans_on_load(self) -> None:
        """Identifica jobs órfãos no boot.

        Um processo recém-iniciado nao tem thread alguma orquestrando lotes; logo,
        qualquer job carregado como 'running'/'queued' ficou orfao num restart da API
        (os jobs NAO sobrevivem ao restart). Marca como 'interrupted' para que nunca
        sejam confundidos com execucao real e possam ser reprocessados.
        """
        changed = 0
        for batch in self._batches.values():
            for job in batch.jobs:
                if job.status in ("running", "queued"):
                    job.status = "interrupted"
                    job.stage = "interrupted"
                    job.error = "Interrompido por reinício da API (job em andamento não sobrevive ao restart). Reprocessar."
                    job.finished_at = job.finished_at or now_iso()
                    job.updated_at = now_iso()
                    changed += 1
        if changed:
            self._save_locked()

    def _save_locked(self) -> None:
        payload = {"batches": [batch.to_dict() for batch in self._batches.values()]}
        tmp = self.state_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.state_file)


VIDEO_NAME_EXTENSIONS = {".mp4", ".mkv", ".mov", ".webm", ".m4v"}


def sanitize_output_filename(name: str) -> str:
    """Normaliza um nome de arquivo de saida fornecido pelo usuario.

    Remove componentes de caminho e caracteres invalidos e garante extensao de video.
    """
    clean = (name or "").strip().replace("\\", "/")
    clean = clean.split("/")[-1]  # nunca permite subpastas/escapar do destino
    clean = re.sub(r"[\x00-\x1f]", "", clean)
    clean = re.sub(r'[<>:"|?*]', "", clean)
    clean = re.sub(r"\s+", " ", clean).strip().strip(".").strip()
    if not clean:
        raise ValueError("Nome de arquivo invalido.")
    _, ext = os.path.splitext(clean)
    if ext.lower() not in VIDEO_NAME_EXTENSIONS:
        clean = f"{clean}.mp4"
    return clean


def build_download_filenames(clean_urls: list[str], filenames: list[str] | None) -> list[str]:
    """Resolve o nome de cada job: nome custom (posicional) ou 01-NN automatico."""
    width = max(2, len(str(len(clean_urls))))
    raw = list(filenames or [])
    result: list[str] = []
    for index, _url in enumerate(clean_urls, start=1):
        custom = raw[index - 1].strip() if index - 1 < len(raw) else ""
        result.append(sanitize_output_filename(custom) if custom else f"{index:0{width}d}.mp4")
    duplicates = sorted({name for name in result if result.count(name) > 1})
    if duplicates:
        raise ValueError(f"Nomes de arquivo duplicados no lote: {', '.join(duplicates[:5])}")
    return result


def normalize_data_destination(destination: str) -> str:
    clean = (destination or "/data/downloads").strip()
    if clean == "/data":
        return clean
    if not clean.startswith("/data/"):
        raise ValueError("O destino deve ficar dentro de /data.")
    parts = [part for part in clean.split("/") if part]
    normalized = "/" + "/".join(parts)
    return normalized


def normalize_data_container_path(path: str) -> str:
    clean = (path or "/data").strip()
    if clean == "/data":
        return clean
    if not clean.startswith("/data/"):
        raise ValueError("O caminho deve ficar dentro de /data.")
    parts = [part for part in clean.split("/") if part]
    return "/" + "/".join(parts)


def resolve_data_path(data_root: Path, container_path: str) -> Path:
    clean = normalize_data_container_path(container_path)
    if clean == "/data":
        return data_root.resolve()
    relative = clean.removeprefix("/data/").strip("/")
    path = (data_root / relative).resolve()
    data_root = data_root.resolve()
    if data_root != path and data_root not in path.parents:
        raise ValueError("Caminho fora de /data.")
    return path


def to_container_data_path(data_root: Path, path: Path) -> str:
    data_root = data_root.resolve()
    resolved = path.resolve()
    if resolved == data_root:
        return "/data"
    return "/data/" + str(resolved.relative_to(data_root)).replace(os.sep, "/")


def default_destination_for_source(data_root: Path, source_path: str) -> str:
    resolved = resolve_data_path(data_root, source_path)
    if resolved.is_file():
        return to_container_data_path(data_root, resolved.parent)
    return normalize_data_container_path(source_path)


def list_local_media_files(data_root: Path, source_path: str) -> list[dict[str, str]]:
    root = resolve_data_path(data_root, source_path)
    if not root.exists():
        raise ValueError(f"Caminho nao encontrado: {source_path}")

    if root.is_file():
        candidates = [root]
    elif root.is_dir():
        candidates = sorted(
            (path for path in root.rglob("*") if path.is_file()),
            key=lambda path: str(path).lower(),
        )
    else:
        raise ValueError(f"Caminho invalido: {source_path}")

    media_files = [
        path
        for path in candidates
        if path.suffix.lower() in LOCAL_MEDIA_EXTENSIONS and not _is_hidden_or_sensitive(data_root, path)
    ]
    if not media_files:
        raise ValueError(f"Nenhum video encontrado em: {source_path}")

    return [{"path": to_container_data_path(data_root, path), "name": path.name} for path in media_files]


def _is_hidden_or_sensitive(data_root: Path, path: Path) -> bool:
    relative_parts = path.resolve().relative_to(data_root.resolve()).parts
    return any(part.startswith(".") or part in SENSITIVE_FILE_NAMES for part in relative_parts)


def normalize_cookie_to_vdl_token(cookie: str | None) -> str | None:
    value = (cookie or "").strip()
    if not value:
        return None

    compact = re.sub(r"\s+", "", value)
    decoded = _try_b64decode(compact)
    if decoded and (_looks_like_json(decoded) or ";" in decoded):
        return compact

    if _looks_like_json(value):
        return base64.b64encode(value.encode("utf-8")).decode("ascii")

    if _looks_like_cookie_header(value):
        legacy = f"Mozilla/5.0;{value}"
        return base64.b64encode(legacy.encode("utf-8")).decode("ascii")

    return base64.b64encode(value.encode("utf-8")).decode("ascii")


def processing_args(mode: ProcessingMode) -> list[str]:
    if mode == "download":
        return ["--only-download"]
    if mode == "transcribe":
        return ["--transcribe"]
    if mode == "context":
        return ["--context"]
    if mode == "unified":
        return ["--unified-mode"]
    raise ValueError(f"Modo de processamento invalido: {mode}")


def local_processing_args(mode: ProcessingMode) -> list[str]:
    if mode == "transcribe":
        return ["--transcribe"]
    if mode == "context":
        return ["--context"]
    if mode == "unified":
        return ["--unified-mode"]
    raise ValueError("Modo local deve ser 'transcribe', 'context' ou 'unified'.")


def _try_b64decode(value: str) -> str | None:
    try:
        return base64.b64decode(value, validate=True).decode("utf-8")
    except Exception:
        return None


def _looks_like_json(value: str) -> bool:
    text = value.strip()
    if not (text.startswith("[") and text.endswith("]")):
        return False
    try:
        return isinstance(json.loads(text), list)
    except json.JSONDecodeError:
        return False


def _looks_like_cookie_header(value: str) -> bool:
    if "\n" in value or "[" in value or "{" in value:
        return False
    return bool(re.search(r"(^|;\s*)[^=;\s]+=[^;]+", value))
