"""HTTP endpoints.

``create_router`` builds an ``APIRouter`` with all endpoints so the app factory never
needs editing to add a route. Checkpoint 6 lands ``POST /uploads``; the download and
health endpoints are added here in checkpoint 7.

Upload flow (security-critical ordering):
1. API-key dependency (constant-time) — 401 on failure.
2. ``request.form(max_part_size=MAX_UPLOAD_BYTES, max_files=1)`` — Starlette aborts an
   oversize part mid-stream (→ 413) rather than buffering the whole body.
3. Exactly one non-empty file part (→ 400 otherwise).
4. Extension allow-list (→ 415).
5. Sniff the head, resolve the server-side type (→ 415 on content/extension mismatch).
6. Stream to quarantine under a random name (atomic publish), then insert metadata
   (committed only after the file is durable). On insert failure the published file is
   unlinked (no dangling capability).
"""

from __future__ import annotations

import logging
import time
from datetime import timedelta
from functools import partial

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    status,
)
from fastapi.responses import FileResponse
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException

from .auth import require_api_key
from .config import Settings
from .errors import (
    EmptyUpload,
    FileTooLarge,
    TypeNotAllowed,
)
from .logging import log_request
from .metadata import (
    StoredObject,
    connect,
    get_object,
    insert_object,
    utcnow,
)
from .storage import (
    open_within_root,
    store_stream,
)
from .tokens import new_token
from .validation import (
    check_extension,
    content_disposition,
    resolve_type,
)

_SNIFF_SIZE = 8192  # bytes read from the head for content-signature / text-safety checks


class UploadResponse(BaseModel):
    token: str
    original_name: str
    content_type: str
    size: int
    sha256: str
    expires_at: str


def _too_large_or_bad_request(exc: MultiPartException) -> HTTPException:
    # Starlette pins these messages (v1.3.1): size breaches say "maximum size".
    if "maximum size" in str(exc):
        return HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "upload too large")
    return HTTPException(status.HTTP_400_BAD_REQUEST, "malformed or multi-part upload")


def create_router(settings: Settings, logger: logging.Logger) -> APIRouter:
    router = APIRouter()
    api_key_dep = require_api_key(settings)

    @router.post("/uploads", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
    async def upload(request: Request, _: None = Depends(api_key_dep)) -> UploadResponse:
        started = time.monotonic()
        try:
            form = await request.form(max_part_size=settings.max_upload_bytes, max_files=1, max_fields=1)
        except MultiPartException as exc:
            raise _too_large_or_bad_request(exc) from exc

        files = [value for value in form.values() if isinstance(value, UploadFile)]
        if len(files) != 1:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "exactly one file part is required")
        upload_file = files[0]

        try:
            ext = check_extension(upload_file.filename or "", settings.allowed_types)
            head = await upload_file.read(_SNIFF_SIZE)
            if not head:
                raise EmptyUpload("upload is empty")
            content_type = resolve_type(ext, head, settings.allowed_types)
            await upload_file.seek(0)

            result = await run_in_threadpool(
                partial(store_stream, settings.quarantine_dir, upload_file.file, max_bytes=settings.max_upload_bytes)
            )
        except TypeNotAllowed as exc:
            raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, str(exc)) from exc
        except FileTooLarge as exc:
            raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "upload too large") from exc
        except EmptyUpload as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "upload is empty") from exc

        created = utcnow()
        obj = StoredObject(
            token=new_token(),
            stored_name=result.stored_name,
            original_name=upload_file.filename or "download",
            content_type=content_type,
            size=result.size,
            sha256=result.sha256,
            created_at=created,
            expires_at=created + timedelta(seconds=settings.token_ttl_seconds),
        )
        conn = connect(settings.db_path)
        try:
            insert_object(conn, obj)
        except Exception as exc:
            # Never leave a published file without a committed token.
            open_within_root(settings.quarantine_dir, result.stored_name).unlink(missing_ok=True)
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "could not persist upload") from exc
        finally:
            conn.close()

        log_request(
            logger,
            method="POST",
            route="/uploads",
            status=status.HTTP_201_CREATED,
            size_bytes=obj.size,
            duration_ms=(time.monotonic() - started) * 1000,
        )
        return UploadResponse(
            token=obj.token,
            original_name=obj.original_name,
            content_type=obj.content_type,
            size=obj.size,
            sha256=obj.sha256,
            expires_at=obj.expires_at.isoformat(),
        )

    @router.get("/downloads/{token}")
    async def download(token: str) -> FileResponse:
        started = time.monotonic()
        conn = connect(settings.db_path)
        try:
            obj = get_object(conn, token)
        finally:
            conn.close()
        # Unknown and expired are indistinguishable: identical 404, no timing/body tell.
        if obj is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
        path = open_within_root(settings.quarantine_dir, obj.stored_name)
        if not path.is_file():
            raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
        log_request(
            logger,
            method="GET",
            route="/downloads/{token}",
            status=status.HTTP_200_OK,
            size_bytes=obj.size,
            duration_ms=(time.monotonic() - started) * 1000,
        )
        return FileResponse(
            path,
            media_type=obj.content_type,
            headers={
                "Content-Disposition": content_disposition(obj.original_name),
                "X-Content-Type-Options": "nosniff",
            },
        )

    @router.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return router
