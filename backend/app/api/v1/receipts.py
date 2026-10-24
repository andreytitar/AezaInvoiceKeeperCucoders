from __future__ import annotations

import uuid
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, File, Form, Response, UploadFile, status
from fastapi.responses import FileResponse

from app.api.deps import ContainerDep, DbDep, UserDep
from app.api.errors import responses
from app.schemas.receipts import ReceiptOut
from app.services.receipts import ReceiptService

router = APIRouter(prefix="/payment-occurrences/{occurrence_id}/receipt", tags=["receipts"])


@router.get("", response_model=ReceiptOut, summary="Чек периода", responses=responses(401, 404))
def get_receipt(occurrence_id: uuid.UUID, user: UserDep, c: ContainerDep, db: DbDep) -> ReceiptOut:
    return ReceiptOut.build(ReceiptService(db, c.clock, c.settings).get(occurrence_id, user.team_id))


@router.put(
    "",
    response_model=ReceiptOut,
    summary="Прикрепить/заменить чек: ссылка и/или файл",
    description="multipart/form-data: `url` (http/https) и/или `file` (PNG, JPG, PDF до 5 МБ; тип проверяется "
    "по содержимому). Переданная часть заменяет прежнюю, непереданная сохраняется.",
    responses={**responses(401, 404, 422), 413: {"description": "Файл больше 5 МБ"}},
)
async def put_receipt(
    occurrence_id: uuid.UUID,
    user: UserDep,
    c: ContainerDep,
    db: DbDep,
    url: Annotated[str | None, Form(max_length=2000)] = None,
    file: Annotated[UploadFile | None, File()] = None,
) -> ReceiptOut:
    data = None
    name = None
    if file is not None and file.filename:
        data = await file.read(c.settings.receipt_max_bytes + 1)
        name = file.filename
    r = ReceiptService(db, c.clock, c.settings).upsert(
        occurrence_id, url=url or None, file_bytes=data, file_name=name, actor=user
    )
    return ReceiptOut.build(r)


@router.delete(
    "", status_code=status.HTTP_204_NO_CONTENT, summary="Удалить чек", responses=responses(401, 404)
)
def delete_receipt(occurrence_id: uuid.UUID, user: UserDep, c: ContainerDep, db: DbDep) -> Response:
    ReceiptService(db, c.clock, c.settings).delete(occurrence_id, actor=user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/file",
    summary="Скачать файл чека (только авторизованным)",
    response_class=FileResponse,
    responses={**responses(401, 404), 200: {"content": {"application/pdf": {}, "image/png": {}, "image/jpeg": {}}}},
)
def download_receipt(occurrence_id: uuid.UUID, user: UserDep, c: ContainerDep, db: DbDep) -> FileResponse:
    path, r = ReceiptService(db, c.clock, c.settings).file(occurrence_id, user.team_id)
    return FileResponse(
        path,
        media_type=r.mime,
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{quote(r.file_name or path.name)}",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
            "Content-Security-Policy": "default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; sandbox",
        },
    )
