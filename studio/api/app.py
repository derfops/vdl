from __future__ import annotations

import mimetypes
import os
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from auth import AuthError, AuthManager
from orchestrator import (
    FileExplorer,
    JobManager,
    LocalProcessingMode,
    RuntimeMode,
    RuntimeOrchestrator,
    normalize_data_destination,
)


PROJECT_ROOT = Path(os.getenv("VDL_PROJECT_ROOT", ".")).resolve()
DATA_ROOT = Path(os.getenv("VDL_DATA_ROOT", PROJECT_ROOT / "data")).resolve()
STATE_DIR = Path(os.getenv("VDL_STUDIO_STATE_DIR", DATA_ROOT / ".vdl-studio-web")).resolve()

app = FastAPI(title="VDL Studio API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

orchestrator = RuntimeOrchestrator(PROJECT_ROOT)
files = FileExplorer(DATA_ROOT)
jobs = JobManager(DATA_ROOT, orchestrator)
auth_manager = AuthManager(STATE_DIR)


def _bearer(authorization: str | None) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


def require_auth(authorization: str | None = Header(default=None)) -> None:
    if not auth_manager.validate(_bearer(authorization)):
        raise HTTPException(status_code=401, detail="Nao autenticado.")


class LoginRequest(BaseModel):
    username: str
    password: str


class ChangePasswordRequest(BaseModel):
    current: str
    new: str


@app.post("/api/auth/login")
def auth_login(request: LoginRequest) -> dict[str, object]:
    try:
        return auth_manager.login(request.username, request.password)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@app.get("/api/auth/me")
def auth_me(authorization: str | None = Header(default=None)) -> dict[str, object]:
    try:
        return auth_manager.me(_bearer(authorization))
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@app.post("/api/auth/change-password")
def auth_change_password(
    request: ChangePasswordRequest, authorization: str | None = Header(default=None)
) -> dict[str, object]:
    try:
        return auth_manager.change_password(_bearer(authorization), request.current, request.new)
    except AuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/auth/logout")
def auth_logout(authorization: str | None = Header(default=None)) -> dict[str, object]:
    auth_manager.logout(_bearer(authorization))
    return {"ok": True}


class RuntimeRequest(BaseModel):
    mode: RuntimeMode
    rebuild: bool = False


class StopRuntimeRequest(BaseModel):
    mode: RuntimeMode


class CreateDirectoryRequest(BaseModel):
    path: str = "/data/downloads"


class BatchDownloadRequest(BaseModel):
    mode: RuntimeMode
    urls: list[str] = Field(default_factory=list)
    destination: str = "/data/downloads"
    cookie: str | None = None
    concurrency: int = Field(default=1, ge=1, le=4)
    processing_mode: Literal["download", "transcribe", "context", "unified"] = "download"


class LocalTranscriptionRequest(BaseModel):
    mode: RuntimeMode
    source_path: str = "/data/downloads"
    destination: str | None = None
    concurrency: int = Field(default=1, ge=1, le=2)
    processing_mode: LocalProcessingMode = "transcribe"
    use_gpu: bool = False
    whisper_model: Literal["tiny", "base", "small", "medium", "large"] = "base"


@app.get("/api/health")
def health() -> dict[str, object]:
    return {"ok": True, "project_root": str(PROJECT_ROOT), "data_root": str(DATA_ROOT)}


@app.get("/api/runtime/status", dependencies=[Depends(require_auth)])
def runtime_status() -> dict[str, object]:
    return orchestrator.status()


@app.post("/api/runtime/start", dependencies=[Depends(require_auth)])
def start_runtime(request: RuntimeRequest) -> dict[str, object]:
    result = orchestrator.start(request.mode, rebuild=request.rebuild)
    if not result["result"]["ok"]:
        raise HTTPException(status_code=500, detail=result)
    return result


@app.post("/api/runtime/stop", dependencies=[Depends(require_auth)])
def stop_runtime(request: StopRuntimeRequest) -> dict[str, object]:
    result = orchestrator.stop(request.mode)
    if not result["result"]["ok"]:
        raise HTTPException(status_code=500, detail=result)
    return result


@app.get("/api/runtime/ip", dependencies=[Depends(require_auth)])
def runtime_ip(mode: RuntimeMode) -> dict[str, object]:
    return orchestrator.public_ip(mode)


@app.get("/api/runtime/logs", dependencies=[Depends(require_auth)])
def runtime_logs(mode: RuntimeMode, tail: int = Query(default=160, ge=20, le=1000)) -> dict[str, object]:
    result = orchestrator.logs(mode, tail=tail)
    if not result["result"]["ok"]:
        raise HTTPException(status_code=404, detail=result)
    return result


@app.get("/api/files", dependencies=[Depends(require_auth)])
def list_files(path: str = "/data") -> dict[str, object]:
    try:
        return files.list_path(path)
    except (ValueError, FileNotFoundError, NotADirectoryError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/files/preview")
def preview_file(path: str, token: str | None = None) -> FileResponse:
    # Carregado direto em <video>/<img>/<iframe> src, que nao enviam header
    # Authorization: por isso o token vem por query param.
    if not auth_manager.validate(token):
        raise HTTPException(status_code=401, detail="Nao autenticado.")
    try:
        file_path = files.resolve_preview_file(path)
    except (ValueError, FileNotFoundError, IsADirectoryError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    media_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    return FileResponse(file_path, media_type=media_type)


@app.post("/api/files/directory", dependencies=[Depends(require_auth)])
def create_directory(request: CreateDirectoryRequest) -> dict[str, object]:
    try:
        return files.create_directory(request.path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/jobs/download-batch", dependencies=[Depends(require_auth)])
def create_download_batch(request: BatchDownloadRequest) -> dict[str, object]:
    try:
        normalize_data_destination(request.destination)
        return jobs.create_download_batch(
            mode=request.mode,
            urls=request.urls,
            destination=request.destination,
            cookie=request.cookie,
            concurrency=request.concurrency,
            processing_mode=request.processing_mode,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/jobs/local-transcription-batch", dependencies=[Depends(require_auth)])
def create_local_transcription_batch(request: LocalTranscriptionRequest) -> dict[str, object]:
    try:
        return jobs.create_local_transcription_batch(
            mode=request.mode,
            source_path=request.source_path,
            destination=request.destination,
            concurrency=request.concurrency,
            processing_mode=request.processing_mode,
            use_gpu=request.use_gpu,
            whisper_model=request.whisper_model,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/jobs", dependencies=[Depends(require_auth)])
def list_jobs() -> dict[str, object]:
    return jobs.list_batches()
