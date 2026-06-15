from __future__ import annotations

import base64
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from vdl_studio.credentials import mask_secret, resolve_pasted_auth
from vdl_studio.cli import StudioCallbacks, _run_download_jobs
from vdl_studio.filenames import ordered_filenames
from vdl_studio.models import Batch, Job, JobStage, JobState
from vdl_studio.state import StudioStateStore


def fake_cookie_extractor(raw: str):
    cookies = json.loads(raw)
    header = "; ".join(f"{cookie['name']}={cookie['value']}" for cookie in cookies)
    return "TestAgent", header, "https://example.com/", cookies


class FilenameTests(unittest.TestCase):
    def test_generates_two_digit_names_by_default(self) -> None:
        self.assertEqual(ordered_filenames(3), ["01.mp4", "02.mp4", "03.mp4"])

    def test_grows_width_for_large_batches(self) -> None:
        names = ordered_filenames(120)
        self.assertEqual(names[0], "001.mp4")
        self.assertEqual(names[-1], "120.mp4")

    def test_normalizes_extension(self) -> None:
        self.assertEqual(ordered_filenames(1, "mkv"), ["01.mkv"])


class CredentialTests(unittest.TestCase):
    def test_detects_raw_json_cookies(self) -> None:
        raw = '[{"name": "session", "value": "abc"}]'
        auth = resolve_pasted_auth(raw, fake_cookie_extractor)
        self.assertIsNotNone(auth)
        self.assertEqual(auth.cookie_header, "session=abc")
        self.assertEqual(auth.referer, "https://example.com/")

    def test_detects_base64_json_cookies(self) -> None:
        raw = '[{"name": "session", "value": "abc"}]'
        encoded = base64.b64encode(raw.encode("utf-8")).decode("ascii")
        auth = resolve_pasted_auth(encoded, fake_cookie_extractor)
        self.assertIsNotNone(auth)
        self.assertEqual(auth.source_label, "entrada colada (base64)")

    def test_rejects_invalid_secret(self) -> None:
        self.assertIsNone(resolve_pasted_auth("not-a-cookie", fake_cookie_extractor))

    def test_detects_plain_cookie_header(self) -> None:
        auth = resolve_pasted_auth("session=abc; other=def", fake_cookie_extractor)
        self.assertIsNotNone(auth)
        self.assertEqual(auth.cookie_header, "session=abc; other=def")

    def test_masks_secrets(self) -> None:
        self.assertEqual(mask_secret("abcdefghijklmnop"), "abcd************mnop")


class StateStoreTests(unittest.TestCase):
    def test_writes_and_reads_latest_jobs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = StudioStateStore(Path(tmpdir))
            job = Job(
                batch_id="batch_1",
                job_id="job_001",
                position=1,
                url="https://example.com/video.m3u8",
                output_filename="01.mp4",
            )
            batch = Batch(batch_id="batch_1", destination="/tmp", jobs=[job])
            store.append_batch(batch)
            store.append_queued_job(job)
            store.transition(job, JobState.RUNNING, JobStage.DOWNLOAD, increment_attempt=True)

            jobs = store.latest_jobs("batch_1")
            self.assertEqual(len(jobs), 1)
            self.assertEqual(jobs[0].status, JobState.RUNNING)
            self.assertEqual(jobs[0].attempt, 1)
            self.assertEqual(len((Path(tmpdir) / "download_queue.jsonl").read_text().splitlines()), 1)

    def test_latest_jobs_do_not_collide_across_batches(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = StudioStateStore(Path(tmpdir))
            first = Job(
                batch_id="batch_1",
                job_id="job_001",
                position=1,
                url="https://example.com/1.m3u8",
                output_filename="01.mp4",
            )
            second = Job(
                batch_id="batch_2",
                job_id="job_001",
                position=1,
                url="https://example.com/2.m3u8",
                output_filename="01.mp4",
            )
            store.append_queued_job(first)
            store.append_queued_job(second)
            store.transition(first, JobState.SUCCEEDED, JobStage.FINALIZE)
            store.transition(second, JobState.FAILED, JobStage.DOWNLOAD)

            jobs = store.latest_jobs()
            self.assertEqual(len(jobs), 2)

    def test_download_runner_processes_pending_jobs_with_worker_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = StudioStateStore(Path(tmpdir) / "state")
            destination = Path(tmpdir) / "downloads"
            destination.mkdir()
            jobs = [
                Job(
                    batch_id="batch_1",
                    job_id=f"job_{index:03d}",
                    position=index,
                    url=f"https://example.com/{index}.m3u8",
                    output_filename=f"{index:02d}.mp4",
                )
                for index in range(1, 4)
            ]
            batch = Batch(batch_id="batch_1", destination=str(destination), jobs=jobs)
            for job in jobs:
                store.append_queued_job(job)

            def fake_download(url, output_path, user_agent, cookie_header, referer, cookies_list):
                Path(output_path).write_text(url, encoding="utf-8")
                return True

            callbacks = StudioCallbacks(
                cookie_extractor=fake_cookie_extractor,
                download_video=fake_download,
                extract_audio=lambda *args: None,
                transcribe_audio_local=lambda *args: None,
                transcribe_and_generate_context_via_api=lambda *args: None,
                generate_context_from_text=lambda *args: None,
                script_dir=str(Path(tmpdir)),
            )

            with contextlib.redirect_stdout(io.StringIO()):
                _run_download_jobs(
                    callbacks,
                    store,
                    batch,
                    auth=None,
                    continue_after_failure=True,
                    max_workers=2,
                )

            latest = store.latest_jobs("batch_1")
            self.assertEqual([job.status for job in latest], [JobState.SUCCEEDED] * 3)
            self.assertTrue((destination / "01.mp4").exists())


if __name__ == "__main__":
    unittest.main()
