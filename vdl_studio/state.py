from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import Batch, Job, JobStage, JobState


@dataclass(frozen=True)
class Event:
    batch_id: str
    job_id: str
    attempt: int
    stage: str
    level: str
    message: str
    ts: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class StudioStateStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.batches_file = self.root / "batches.jsonl"
        self.queue_file = self.root / "download_queue.jsonl"
        self.jobs_file = self.root / "jobs.jsonl"
        self.events_file = self.root / "events.jsonl"
        self._lock = threading.Lock()

    def append_batch(self, batch: Batch) -> None:
        self._append_json(self.batches_file, batch.to_dict())

    def append_queued_job(self, job: Job) -> None:
        data = job.to_dict()
        self._append_json(self.queue_file, data)
        self._append_json(self.jobs_file, data)

    def append_job(self, job: Job) -> None:
        self._append_json(self.jobs_file, job.to_dict())

    def append_event(self, event: Event) -> None:
        self._append_json(self.events_file, event.to_dict())

    def latest_jobs(self, batch_id: str | None = None) -> list[Job]:
        latest: dict[str, dict[str, Any]] = {}
        for record in self._read_jsonl(self.jobs_file):
            if batch_id and record.get("batch_id") != batch_id:
                continue
            key = f"{record['batch_id']}:{record['job_id']}"
            latest[key] = record
        return [Job.from_dict(record) for record in latest.values()]

    def list_batches(self) -> list[Batch]:
        return [Batch.from_dict(record) for record in self._read_jsonl(self.batches_file)]

    def latest_batch_jobs(self, batch: Batch) -> Batch:
        latest = {job.job_id: job for job in self.latest_jobs(batch.batch_id)}
        jobs = [latest.get(job.job_id, job) for job in batch.jobs]
        return Batch(
            batch_id=batch.batch_id,
            destination=batch.destination,
            jobs=jobs,
            created_at=batch.created_at,
        )

    def transition(
        self,
        job: Job,
        status: JobState,
        stage: JobStage | None = None,
        error: str | None = None,
        increment_attempt: bool = False,
    ) -> Job:
        updated = job.transition(
            status=status,
            stage=stage,
            error=error,
            attempt=job.attempt + 1 if increment_attempt else job.attempt,
        )
        self.append_job(updated)
        return updated

    def _append_json(self, path: Path, data: dict[str, Any]) -> None:
        with self._lock:
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(data, ensure_ascii=False) + "\n")

    def _read_jsonl(self, path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        records = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    records.append(json.loads(line))
        return records
