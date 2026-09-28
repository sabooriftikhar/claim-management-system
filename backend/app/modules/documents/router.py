import uuid

from fastapi import APIRouter, Depends, File, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.auth.service import get_current_user
from app.modules.documents import service as docs_svc
from app.modules.documents.schemas import DocumentOut
from app.modules.users.models import User

router = APIRouter()

@router.post(
    "/{claim_id}/documents",
    response_model=DocumentOut,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a document for a claim",
)
async def upload_document(
    claim_id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    doc = await docs_svc.upload_document(db, claim_id, file, current_user)
    return DocumentOut.model_validate(doc)


@router.get(
    "/{claim_id}/documents",
    response_model=list[DocumentOut],
    summary="List all documents for a claim",
)
async def list_documents(
    claim_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    docs = await docs_svc.list_documents(db, claim_id, current_user)
    return [DocumentOut.model_validate(d) for d in docs]


@router.get(
    "/{claim_id}/documents/{document_id}/download",
    summary="Download a specific document",
)
async def download_document(
    claim_id: uuid.UUID,
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    doc = await docs_svc.get_document(db, claim_id, document_id, current_user)
    return Response(
        content=doc.file_data,
        media_type=doc.file_type,
        headers={"Content-Disposition": f'attachment; filename="{doc.file_name}"'},
    )
