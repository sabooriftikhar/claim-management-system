import uuid
from typing import List

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.claims.service import _get_claim_or_404
from app.modules.documents.models import ClaimDocument
from app.modules.users.models import User
from app.shared.enums import UserRole
from app.shared.exceptions import ForbiddenError, NotFoundError

def _check_document_access(claim, actor: User, *, require_assignment: bool = False):
    if actor.role == UserRole.admin:
        return
    if actor.role == UserRole.claimant and claim.claimant_id != actor.id:
        raise ForbiddenError("You can only access documents for your own claims.")
    if (
        actor.role == UserRole.adjuster
        and claim.assigned_to != actor.id
        and (require_assignment or claim.assigned_to is not None)
    ):
        raise ForbiddenError("You can only access documents for claims assigned to you.")

async def upload_document(
    db: AsyncSession, claim_id: uuid.UUID, file: UploadFile, actor: User
) -> ClaimDocument:
    claim = await _get_claim_or_404(db, claim_id)
    _check_document_access(claim, actor, require_assignment=True)

    file_data = await file.read()

    doc = ClaimDocument(
        claim_id=claim.id,
        file_name=file.filename or "unknown",
        file_type=file.content_type or "application/octet-stream",
        file_data=file_data,
        uploaded_by=actor.id,
    )
    db.add(doc)
    await db.flush()
    return doc

async def list_documents(
    db: AsyncSession, claim_id: uuid.UUID, actor: User
) -> List[ClaimDocument]:
    claim = await _get_claim_or_404(db, claim_id)
    _check_document_access(claim, actor)

    q = select(ClaimDocument).where(ClaimDocument.claim_id == claim.id).order_by(ClaimDocument.created_at.asc())
    result = await db.execute(q)
    return list(result.scalars().all())

async def get_document(
    db: AsyncSession, claim_id: uuid.UUID, document_id: uuid.UUID, actor: User
) -> ClaimDocument:
    claim = await _get_claim_or_404(db, claim_id)
    _check_document_access(claim, actor)

    q = select(ClaimDocument).where(ClaimDocument.id == document_id, ClaimDocument.claim_id == claim.id)
    result = await db.execute(q)
    doc = result.scalar_one_or_none()
    if not doc:
        raise NotFoundError("Document")
    return doc
