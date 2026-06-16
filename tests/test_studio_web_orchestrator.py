import base64
import datetime
import json
import tempfile
import time
import unittest
from pathlib import Path

from studio.api.orchestrator import (
    BatchRecord,
    CommandResult,
    FileExplorer,
    JobManager,
    JobRecord,
    build_download_filenames,
    list_local_media_files,
    local_processing_args,
    normalize_cookie_to_vdl_token,
    normalize_data_destination,
    now_iso,
    processing_args,
    sanitize_output_filename,
)


class FakeRunner:
    """Captura chamadas docker e devolve sucesso, sem tocar em Docker real."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def docker(self, *args: str, timeout: int = 60, env=None) -> CommandResult:
        self.calls.append(list(args))
        return CommandResult(list(args), 0, "ok", "")


class FakeOrchestrator:
    def __init__(self, ready: bool = True) -> None:
        self.runner = FakeRunner()
        self._ready = ready

    def runtime_status(self, mode: str) -> dict:
        return {"ready": self._ready, "worker": {"running": self._ready}}


def _wait_until(predicate, timeout: float = 5.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return
        time.sleep(0.02)


def _make_blocked_batch(manager: JobManager, batch_id: str, statuses, job_type: str = "download") -> BatchRecord:
    jobs = [
        JobRecord(
            job_id=f"job-{i:02d}",
            batch_id=batch_id,
            mode="none",
            position=i,
            url=f"https://example.com/{i:02d}.mpd",
            filename=f"{i:02d}.mp4",
            destination="/data/downloads",
            processing_mode="download",
            job_type=job_type,
            status=status,
            stage=status,
        )
        for i, status in enumerate(statuses, start=1)
    ]
    batch = BatchRecord(
        batch_id=batch_id,
        mode="none",
        destination="/data/downloads",
        processing_mode="download",
        concurrency=2,
        created_at=now_iso(),
        jobs=jobs,
        job_type=job_type,
    )
    manager._batches[batch_id] = batch
    return batch


class StudioWebOrchestratorTests(unittest.TestCase):
    def test_normalize_destination_requires_data_root(self):
        self.assertEqual(normalize_data_destination("/data/downloads"), "/data/downloads")
        self.assertEqual(normalize_data_destination("/data/aulas/"), "/data/aulas")
        with self.assertRaises(ValueError):
            normalize_data_destination("/tmp/downloads")

    def test_cookie_header_becomes_legacy_vdl_token(self):
        token = normalize_cookie_to_vdl_token("session=abc; other=def")
        decoded = base64.b64decode(token).decode("utf-8")
        self.assertEqual(decoded, "Mozilla/5.0;session=abc; other=def")

    def test_json_cookie_becomes_base64_json(self):
        raw = '[{"domain":".example.com","name":"session","value":"abc"}]'
        token = normalize_cookie_to_vdl_token(raw)
        self.assertEqual(base64.b64decode(token).decode("utf-8"), raw)

    def test_existing_base64_json_is_preserved(self):
        raw = '[{"name":"session","value":"abc"}]'
        token = base64.b64encode(raw.encode("utf-8")).decode("ascii")
        self.assertEqual(normalize_cookie_to_vdl_token(token), token)

    def test_processing_args_are_mutually_exclusive(self):
        self.assertEqual(processing_args("download"), ["--only-download"])
        self.assertEqual(processing_args("transcribe"), ["--transcribe"])
        self.assertEqual(processing_args("context"), ["--context"])
        self.assertEqual(processing_args("unified"), ["--unified-mode"])

    def test_download_batch_requires_cookie_in_studio_api(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = JobManager(Path(tmpdir), orchestrator=object())
            with self.assertRaisesRegex(ValueError, "Cookie obrigatorio"):
                manager.create_download_batch(
                    mode="none",
                    urls=["https://example.com/video.mpd"],
                    destination="/data/downloads",
                    cookie=None,
                    concurrency=1,
                    processing_mode="download",
                )

    def test_local_processing_args_accept_only_transcription_modes(self):
        self.assertEqual(local_processing_args("transcribe"), ["--transcribe"])
        self.assertEqual(local_processing_args("context"), ["--context"])
        self.assertEqual(local_processing_args("unified"), ["--unified-mode"])
        with self.assertRaises(ValueError):
            local_processing_args("download")

    def test_list_local_media_files_scans_only_supported_video_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data_root = Path(tmpdir)
            course = data_root / "course"
            nested = course / "nested"
            hidden = course / ".hidden"
            nested.mkdir(parents=True)
            hidden.mkdir()
            (course / "01.mp4").write_text("video", encoding="utf-8")
            (nested / "02.mkv").write_text("video", encoding="utf-8")
            (course / "notes.txt").write_text("notes", encoding="utf-8")
            (hidden / "03.mp4").write_text("video", encoding="utf-8")

            files = list_local_media_files(data_root, "/data/course")

            self.assertEqual(
                [item["path"] for item in files],
                ["/data/course/01.mp4", "/data/course/nested/02.mkv"],
            )

    def test_preview_file_resolves_visible_file_inside_data(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data_root = Path(tmpdir)
            video = data_root / "course" / "01.mp4"
            video.parent.mkdir()
            video.write_text("video", encoding="utf-8")

            explorer = FileExplorer(data_root)

            self.assertEqual(explorer.resolve_preview_file("/data/course/01.mp4"), video.resolve())

    def test_preview_file_rejects_sensitive_or_hidden_paths(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data_root = Path(tmpdir)
            (data_root / "cookie.txt").write_text("secret", encoding="utf-8")
            hidden = data_root / ".private"
            hidden.mkdir()
            (hidden / "01.mp4").write_text("video", encoding="utf-8")

            explorer = FileExplorer(data_root)

            with self.assertRaises(ValueError):
                explorer.resolve_preview_file("/data/cookie.txt")
            with self.assertRaises(ValueError):
                explorer.resolve_preview_file("/data/.private/01.mp4")
            with self.assertRaises(ValueError):
                explorer.resolve_preview_file("/tmp/01.mp4")


class BatchLifecycleTests(unittest.TestCase):
    def test_create_download_batch_is_rejected_when_runtime_not_ready(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = JobManager(Path(tmpdir), orchestrator=FakeOrchestrator(ready=False))
            with self.assertRaisesRegex(ValueError, "nao esta iniciado"):
                manager.create_download_batch(
                    mode="none",
                    urls=["https://example.com/video.mpd"],
                    destination="/data/downloads",
                    cookie="session=abc",
                    concurrency=1,
                    processing_mode="download",
                )
            # Nenhum lote deve ter sido criado (sem jobs 'bloqueados' para limpar depois).
            self.assertEqual(manager.list_batches()["batches"], [])

    def test_download_filenames_follow_input_order_regardless_of_completion(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            orchestrator = FakeOrchestrator(ready=True)
            manager = JobManager(Path(tmpdir), orchestrator=orchestrator)
            urls = [
                "https://example.com/aula-intro.mpd",
                "https://example.com/aula-modulo1.mpd",
                "https://example.com/aula-modulo2.mpd",
            ]
            batch = manager.create_download_batch(
                mode="none",
                urls=urls,
                destination="/data/curso",
                cookie="session=abc",
                concurrency=3,  # paralelo: completam fora de ordem
                processing_mode="download",
            )

            # O nome de cada job e fixado pela posicao na lista de entrada.
            self.assertEqual([job["filename"] for job in batch["jobs"]], ["01.mp4", "02.mp4", "03.mp4"])
            self.assertEqual([job["url"] for job in batch["jobs"]], urls)

            _wait_until(lambda: all(
                job["status"] in {"succeeded", "failed", "blocked", "canceled"}
                for b in manager.list_batches()["batches"]
                for job in b["jobs"]
            ))

            # O worker foi invocado com o filename correto POR URL, mesmo em paralelo.
            url_to_filename = {}
            for call in orchestrator.runner.calls:
                if "vdl" in call:
                    cmd = call.index("vdl")
                    url_to_filename[call[cmd + 1]] = call[cmd + 2]
            self.assertEqual(url_to_filename[urls[0]], "01.mp4")
            self.assertEqual(url_to_filename[urls[1]], "02.mp4")
            self.assertEqual(url_to_filename[urls[2]], "03.mp4")

    def test_delete_batch_removes_blocked_jobs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = JobManager(Path(tmpdir), orchestrator=FakeOrchestrator())
            _make_blocked_batch(manager, "batch-x", ["blocked", "blocked", "blocked"])

            result = manager.delete_batch("batch-x")

            self.assertTrue(result["deleted"])
            self.assertEqual(manager.list_batches()["batches"], [])

    def test_delete_batch_rejects_running_jobs_unless_forced(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = JobManager(Path(tmpdir), orchestrator=FakeOrchestrator())
            _make_blocked_batch(manager, "batch-run", ["running", "queued"])

            with self.assertRaisesRegex(ValueError, "em execucao"):
                manager.delete_batch("batch-run")

            manager.delete_batch("batch-run", force=True)
            self.assertEqual(manager.list_batches()["batches"], [])

    def test_delete_missing_batch_raises_keyerror(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = JobManager(Path(tmpdir), orchestrator=FakeOrchestrator())
            with self.assertRaises(KeyError):
                manager.delete_batch("nope")

    def test_cancel_batch_marks_queued_jobs_canceled(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            orchestrator = FakeOrchestrator()
            manager = JobManager(Path(tmpdir), orchestrator=orchestrator)
            _make_blocked_batch(manager, "batch-c", ["queued", "queued", "running"])

            result = manager.cancel_batch("batch-c")

            self.assertEqual(result["canceled"], 3)
            jobs = manager.list_batches()["batches"][0]["jobs"]
            self.assertEqual(jobs[0]["status"], "canceled")
            self.assertEqual(jobs[1]["status"], "canceled")
            # job em execucao foi sinalizado e recebeu pkill no worker (best-effort)
            self.assertTrue(manager._is_cancelled("batch-c", "job-03"))
            self.assertTrue(any("pkill" in call for call in orchestrator.runner.calls))

    def test_retry_download_batch_requires_cookie(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = JobManager(Path(tmpdir), orchestrator=FakeOrchestrator(ready=True))
            _make_blocked_batch(manager, "batch-r", ["blocked", "failed", "succeeded"])

            with self.assertRaisesRegex(ValueError, "Cookie obrigatorio"):
                manager.retry_batch("batch-r")

    def test_retry_reopens_only_unfinished_jobs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = JobManager(Path(tmpdir), orchestrator=FakeOrchestrator(ready=True))
            _make_blocked_batch(manager, "batch-r2", ["blocked", "failed", "succeeded"])

            snapshot = manager.retry_batch("batch-r2", cookie="session=abc")

            self.assertEqual(snapshot["reopened"], 2)
            statuses = {job["job_id"]: job["status"] for job in snapshot["jobs"]}
            self.assertEqual(statuses["job-01"], "queued")
            self.assertEqual(statuses["job-02"], "queued")
            self.assertEqual(statuses["job-03"], "succeeded")  # nao reprocessa o que ja concluiu

            # Drena a thread de reprocessamento antes do teardown do tempdir.
            _wait_until(lambda: all(
                job["status"] in {"succeeded", "failed", "blocked", "canceled"}
                for job in manager.list_batches()["batches"][0]["jobs"]
            ))

    def test_retry_blocked_when_runtime_not_ready(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = JobManager(Path(tmpdir), orchestrator=FakeOrchestrator(ready=False))
            _make_blocked_batch(manager, "batch-r3", ["blocked"])

            with self.assertRaisesRegex(ValueError, "nao esta"):
                manager.retry_batch("batch-r3", cookie="session=abc")


class FilenameTests(unittest.TestCase):
    def test_sanitize_strips_paths_and_adds_extension(self):
        self.assertEqual(sanitize_output_filename("AULA_01"), "AULA_01.mp4")
        self.assertEqual(sanitize_output_filename("01 - Teaser"), "01 - Teaser.mp4")
        self.assertEqual(sanitize_output_filename("../../etc/passwd"), "passwd.mp4")
        self.assertEqual(sanitize_output_filename("aula/final.mkv"), "final.mkv")
        self.assertEqual(sanitize_output_filename('na:me?*.mp4'), "name.mp4")

    def test_sanitize_rejects_empty(self):
        with self.assertRaises(ValueError):
            sanitize_output_filename("   ")

    def test_build_filenames_custom_with_numeric_fallback(self):
        urls = ["https://x/a", "https://x/b", "https://x/c"]
        names = build_download_filenames(urls, ["Teaser", "", "Aula 02.mp4"])
        self.assertEqual(names, ["Teaser.mp4", "02.mp4", "Aula 02.mp4"])

    def test_build_filenames_all_auto_when_empty(self):
        urls = ["https://x/a", "https://x/b"]
        self.assertEqual(build_download_filenames(urls, None), ["01.mp4", "02.mp4"])
        self.assertEqual(build_download_filenames(urls, ["", ""]), ["01.mp4", "02.mp4"])

    def test_build_filenames_rejects_duplicates(self):
        urls = ["https://x/a", "https://x/b"]
        with self.assertRaisesRegex(ValueError, "duplicados"):
            build_download_filenames(urls, ["aula", "aula"])

    def test_create_download_batch_applies_custom_filenames(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            orchestrator = FakeOrchestrator(ready=True)
            manager = JobManager(Path(tmpdir), orchestrator=orchestrator)
            batch = manager.create_download_batch(
                mode="none",
                urls=["https://x/teaser.mpd", "https://x/aula1.mpd"],
                destination="/data/curso",
                cookie="session=abc",
                concurrency=1,
                processing_mode="download",
                filenames=["00 - Teaser", ""],
            )
            self.assertEqual([job["filename"] for job in batch["jobs"]], ["00 - Teaser.mp4", "02.mp4"])
            _wait_until(lambda: all(
                job["status"] in {"succeeded", "failed", "blocked", "canceled"}
                for b in manager.list_batches()["batches"]
                for job in b["jobs"]
            ))


class RetrySingleJobTests(unittest.TestCase):
    def test_retry_single_failed_job_keeps_filename(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            orchestrator = FakeOrchestrator(ready=True)
            manager = JobManager(Path(tmpdir), orchestrator=orchestrator)
            batch = _make_blocked_batch(manager, "batch-rj", ["succeeded", "failed", "succeeded"])
            failed = batch.jobs[1]
            failed.filename = "02-aula.mp4"
            failed.url = "https://example.com/aula.mpd"

            snapshot = manager.retry_job("batch-rj", "job-02", cookie="session=abc")
            self.assertEqual(snapshot["status"], "queued")
            self.assertEqual(snapshot["filename"], "02-aula.mp4")  # mesmo nome

            _wait_until(lambda: all(
                job["status"] in {"succeeded", "failed", "blocked", "canceled", "interrupted"}
                for job in manager.list_batches()["batches"][0]["jobs"]
            ))
            jobs = {j["job_id"]: j for j in manager.list_batches()["batches"][0]["jobs"]}
            self.assertEqual(jobs["job-02"]["status"], "succeeded")
            # só o job pedido rodou; os outros seguem succeeded sem reexecutar
            self.assertEqual(jobs["job-01"]["status"], "succeeded")
            self.assertEqual(jobs["job-03"]["status"], "succeeded")
            # o worker foi chamado com o MESMO filename do job
            call = next(c for c in orchestrator.runner.calls if "vdl" in c and "02-aula.mp4" in c)
            self.assertIn("02-aula.mp4", call)

    def test_retry_single_download_requires_cookie(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = JobManager(Path(tmpdir), orchestrator=FakeOrchestrator(ready=True))
            _make_blocked_batch(manager, "batch-rj2", ["failed"])
            with self.assertRaisesRegex(ValueError, "Cookie obrigatorio"):
                manager.retry_job("batch-rj2", "job-01")

    def test_retry_single_rejects_succeeded_job(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = JobManager(Path(tmpdir), orchestrator=FakeOrchestrator(ready=True))
            _make_blocked_batch(manager, "batch-rj3", ["succeeded"])
            with self.assertRaisesRegex(ValueError, "So e possivel reprocessar"):
                manager.retry_job("batch-rj3", "job-01", cookie="session=abc")


class RenameJobTests(unittest.TestCase):
    def _manager_with_succeeded_file(self, tmpdir):
        data_root = Path(tmpdir)
        (data_root / "curso").mkdir()
        (data_root / "curso" / "01.mp4").write_text("video", encoding="utf-8")
        manager = JobManager(data_root, orchestrator=FakeOrchestrator())
        batch = _make_blocked_batch(manager, "batch-rn", ["succeeded"])
        batch.jobs[0].filename = "01.mp4"
        batch.jobs[0].destination = "/data/curso"
        return manager, data_root

    def test_rename_moves_file_and_updates_record(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manager, data_root = self._manager_with_succeeded_file(tmpdir)
            result = manager.rename_job("batch-rn", "job-01", "Aula 01")
            self.assertEqual(result["filename"], "Aula 01.mp4")
            self.assertFalse((data_root / "curso" / "01.mp4").exists())
            self.assertTrue((data_root / "curso" / "Aula 01.mp4").exists())
            job = manager.list_batches()["batches"][0]["jobs"][0]
            self.assertEqual(job["filename"], "Aula 01.mp4")

    def test_rename_rejects_non_succeeded_job(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = JobManager(Path(tmpdir), orchestrator=FakeOrchestrator())
            _make_blocked_batch(manager, "batch-b", ["blocked"])
            with self.assertRaisesRegex(ValueError, "concluido"):
                manager.rename_job("batch-b", "job-01", "novo")

    def test_rename_rejects_existing_target(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manager, data_root = self._manager_with_succeeded_file(tmpdir)
            (data_root / "curso" / "Aula 01.mp4").write_text("outro", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Ja existe um arquivo"):
                manager.rename_job("batch-rn", "job-01", "Aula 01")


class LocalTranscriptionEngineTests(unittest.TestCase):
    def test_openai_engine_uses_unified_without_whisper_or_gpu(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data_root = Path(tmpdir)
            (data_root / "curso").mkdir()
            (data_root / "curso" / "01.mp4").write_text("video", encoding="utf-8")
            orchestrator = FakeOrchestrator(ready=True)
            manager = JobManager(data_root, orchestrator=orchestrator)

            batch = manager.create_local_transcription_batch(
                mode="none",
                source_path="/data/curso",
                destination="/data/curso",
                concurrency=1,
                processing_mode="unified",
                use_gpu=True,  # deve ser ignorado no modo OpenAI
                whisper_model="large",  # deve ser ignorado no modo OpenAI
            )
            self.assertEqual(batch["processing_mode"], "unified")

            _wait_until(lambda: all(
                job["status"] in {"succeeded", "failed", "blocked", "canceled"}
                for job in manager.list_batches()["batches"][0]["jobs"]
            ))
            call = next(c for c in orchestrator.runner.calls if "vdl" in c)
            self.assertIn("--unified-mode", call)
            self.assertNotIn("--whisper-model", call)
            self.assertNotIn("--gpu", call)
            self.assertIn("--local", call)

    def test_local_whisper_engine_passes_model_and_gpu(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data_root = Path(tmpdir)
            (data_root / "curso").mkdir()
            (data_root / "curso" / "01.mp4").write_text("video", encoding="utf-8")
            orchestrator = FakeOrchestrator(ready=True)
            manager = JobManager(data_root, orchestrator=orchestrator)

            manager.create_local_transcription_batch(
                mode="none",
                source_path="/data/curso",
                destination="/data/curso",
                concurrency=1,
                processing_mode="transcribe",
                use_gpu=True,
                whisper_model="small",
            )
            _wait_until(lambda: all(
                job["status"] in {"succeeded", "failed", "blocked", "canceled"}
                for job in manager.list_batches()["batches"][0]["jobs"]
            ))
            call = next(c for c in orchestrator.runner.calls if "vdl" in c)
            self.assertIn("--transcribe", call)
            self.assertIn("--whisper-model", call)
            self.assertIn("small", call)
            self.assertIn("--gpu", call)


class BootReconciliationTests(unittest.TestCase):
    def _write_state(self, data_root: Path, statuses) -> None:
        state_dir = data_root / ".vdl-studio-web"
        state_dir.mkdir(parents=True, exist_ok=True)
        jobs = [
            {
                "job_id": f"job-{i:02d}", "batch_id": "batch-x", "mode": "none", "position": i,
                "url": f"https://x/{i}", "filename": f"{i:02d}.mp4", "destination": "/data/downloads",
                "processing_mode": "download", "status": st, "stage": st,
            }
            for i, st in enumerate(statuses, start=1)
        ]
        payload = {"batches": [{
            "batch_id": "batch-x", "mode": "none", "destination": "/data/downloads",
            "processing_mode": "download", "concurrency": 1, "created_at": now_iso(),
            "jobs": jobs, "job_type": "download",
        }]}
        (state_dir / "jobs.json").write_text(json.dumps(payload), encoding="utf-8")

    def test_running_and_queued_become_interrupted_on_load(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data_root = Path(tmpdir)
            self._write_state(data_root, ["succeeded", "running", "queued", "failed"])
            manager = JobManager(data_root, orchestrator=FakeOrchestrator())
            statuses = [j["status"] for j in manager.list_batches()["batches"][0]["jobs"]]
            # running/queued órfãos viram 'interrupted'; succeeded/failed intactos
            self.assertEqual(statuses, ["succeeded", "interrupted", "interrupted", "failed"])

    def test_interrupted_jobs_are_retryable(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = JobManager(Path(tmpdir), orchestrator=FakeOrchestrator(ready=True))
            _make_blocked_batch(manager, "batch-i", ["interrupted", "succeeded"])
            snapshot = manager.retry_batch("batch-i", cookie="session=abc")
            self.assertEqual(snapshot["reopened"], 1)
            _wait_until(lambda: all(
                job["status"] in {"succeeded", "failed", "blocked", "canceled", "interrupted"}
                for job in manager.list_batches()["batches"][0]["jobs"]
            ))

    def test_list_batches_includes_server_now(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = JobManager(Path(tmpdir), orchestrator=FakeOrchestrator())
            self.assertIn("server_now", manager.list_batches())

    def test_now_iso_is_timezone_aware(self):
        parsed = datetime.datetime.fromisoformat(now_iso())
        self.assertIsNotNone(parsed.tzinfo)


if __name__ == "__main__":
    unittest.main()
