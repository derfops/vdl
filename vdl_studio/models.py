from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any


class JobState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"


class JobStage(StrEnum):
    VALIDATE_INPUT = "validate_input"
    RESOLVE_CREDENTIALS = "resolve_credentials"
    DOWNLOAD = "download"
    EXTRACT_AUDIO = "extract_audio"
    TRANSCRIBE = "transcribe"
    GENERATE_CONTEXT = "generate_context"
    GENERATE_SUBTITLES = "generate_subtitles"
    CONSOLIDATE_CONTEXTS = "consolidate_contexts"
    FINALIZE = "finalize"


@dataclass(frozen=True)
class Artifact:
    type: str
    path: str
    exists: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Artifact":
        return cls(**data)


@dataclass(frozen=True)
class Job:
    batch_id: str
    job_id: str
    position: int
    url: str
    output_filename: str
    status: JobState = JobState.QUEUED
    stage: JobStage = JobStage.DOWNLOAD
    attempt: int = 0
    artifacts: list[Artifact] = field(default_factory=list)
    error: str | None = None
    updated_at: str = field(default_factory=lambda: _now_iso())

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        data["stage"] = self.stage.value
        data["artifacts"] = [artifact.to_dict() for artifact in self.artifacts]
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Job":
        payload = dict(data)
        payload["status"] = JobState(payload["status"])
        payload["stage"] = JobStage(payload["stage"])
        payload["artifacts"] = [
            Artifact.from_dict(artifact) for artifact in payload.get("artifacts", [])
        ]
        return cls(**payload)

    def transition(
        self,
        status: JobState,
        stage: JobStage | None = None,
        error: str | None = None,
        attempt: int | None = None,
        artifacts: list[Artifact] | None = None,
    ) -> "Job":
        return Job(
            batch_id=self.batch_id,
            job_id=self.job_id,
            position=self.position,
            url=self.url,
            output_filename=self.output_filename,
            status=status,
            stage=stage or self.stage,
            attempt=self.attempt if attempt is None else attempt,
            artifacts=self.artifacts if artifacts is None else artifacts,
            error=error,
            updated_at=_now_iso(),
        )


@dataclass(frozen=True)
class Batch:
    batch_id: str
    destination: str
    jobs: list[Job]
    created_at: str = field(default_factory=lambda: _now_iso())

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["jobs"] = [job.to_dict() for job in self.jobs]
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Batch":
        payload = dict(data)
        payload["jobs"] = [Job.from_dict(job) for job in payload.get("jobs", [])]
        return cls(**payload)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

