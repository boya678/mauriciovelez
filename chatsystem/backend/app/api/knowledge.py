"""
Knowledge base API

Super-admin routes (tenant_id in URL):
  POST   /knowledge/{tenant_id}/upload   — chunk + embed + store a plain-text document
  DELETE /knowledge/{tenant_id}          — delete all chunks for a tenant
  GET    /knowledge/{tenant_id}/status   — return chunk count for a tenant

Tenant-admin routes (tenant resolved from X-Tenant-ID header):
  POST   /knowledge/my/upload            — upload knowledge for own tenant
  DELETE /knowledge/my                   — delete knowledge for own tenant
  GET    /knowledge/my/status            — get knowledge status for own tenant
"""
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_super_admin
from app.db.session import get_db
from app.db.tenant import TenantContext, require_admin, resolve_tenant
from app.services.knowledge import knowledge_status, search_knowledge, upsert_knowledge
from sqlalchemy import text

router = APIRouter(prefix="/knowledge", tags=["knowledge"])
logger = logging.getLogger(__name__)


# ── Schemas ───────────────────────────────────────────────────────────────────

class KnowledgeUpload(BaseModel):
    text: str


class KnowledgeStatusOut(BaseModel):
    tenant_id: str
    chunks: int
    has_knowledge: bool


class KnowledgeUploadOut(BaseModel):
    tenant_id: str
    chunks: int


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _assert_tenant_exists(tenant_id: uuid.UUID, db: AsyncSession) -> None:
    row = await db.execute(
        text("SELECT id FROM public.tenants WHERE id = :tid AND active = true"),
        {"tid": tenant_id},
    )
    if row.fetchone() is None:
        raise HTTPException(status_code=404, detail="Tenant not found or inactive")


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/{tenant_id}/upload", response_model=KnowledgeUploadOut)
async def upload_knowledge(
    tenant_id: uuid.UUID,
    body: KnowledgeUpload,
    db: AsyncSession = Depends(get_db),
    _=Depends(verify_super_admin),
):
    """
    Replace the knowledge base for a tenant with the provided plain text.
    The text is split into ~500-word overlapping chunks, embedded with
    text-embedding-3-large, and stored in pgvector for RAG retrieval.
    """
    if not body.text or not body.text.strip():
        raise HTTPException(status_code=422, detail="Text cannot be empty")

    await _assert_tenant_exists(tenant_id, db)

    try:
        n = await upsert_knowledge(tenant_id, body.text.strip(), db)
    except Exception as exc:
        logger.error("Knowledge upsert failed for tenant %s: %s", tenant_id, exc)
        raise HTTPException(status_code=500, detail="Error processing knowledge base") from exc

    return KnowledgeUploadOut(tenant_id=str(tenant_id), chunks=n)


@router.delete("/{tenant_id}", status_code=204)
async def delete_knowledge(
    tenant_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(verify_super_admin),
):
    """Delete all knowledge chunks for a tenant."""
    await _assert_tenant_exists(tenant_id, db)
    await db.execute(
        text("DELETE FROM public.knowledge_chunks WHERE tenant_id = :tid"),
        {"tid": tenant_id},
    )
    await db.commit()


@router.get("/{tenant_id}/status", response_model=KnowledgeStatusOut)
async def get_knowledge_status(
    tenant_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(verify_super_admin),
):
    """Return the number of chunks stored for a tenant."""
    await _assert_tenant_exists(tenant_id, db)
    n = await knowledge_status(tenant_id, db)
    return KnowledgeStatusOut(
        tenant_id=str(tenant_id),
        chunks=n,
        has_knowledge=n > 0,
    )


# ── Tenant-admin routes (tenant resolved from JWT / X-Tenant-ID header) ───────

@router.post("/my/upload", response_model=KnowledgeUploadOut)
async def my_upload_knowledge(
    body: KnowledgeUpload,
    tenant: TenantContext = Depends(resolve_tenant),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    """Replace the knowledge base for the calling admin's own tenant."""
    if not body.text or not body.text.strip():
        raise HTTPException(status_code=422, detail="Text cannot be empty")

    try:
        n = await upsert_knowledge(tenant.id, body.text.strip(), db)
    except Exception as exc:
        logger.error("Knowledge upsert failed for tenant %s: %s", tenant.id, exc)
        raise HTTPException(status_code=500, detail="Error processing knowledge base") from exc

    return KnowledgeUploadOut(tenant_id=str(tenant.id), chunks=n)


@router.delete("/my", status_code=204)
async def my_delete_knowledge(
    tenant: TenantContext = Depends(resolve_tenant),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    """Delete all knowledge chunks for the calling admin's own tenant."""
    await db.execute(
        text("DELETE FROM public.knowledge_chunks WHERE tenant_id = :tid"),
        {"tid": tenant.id},
    )
    await db.commit()


@router.get("/my/status", response_model=KnowledgeStatusOut)
async def my_knowledge_status(
    tenant: TenantContext = Depends(resolve_tenant),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    """Return the number of chunks stored for the calling admin's own tenant."""
    n = await knowledge_status(tenant.id, db)
    return KnowledgeStatusOut(
        tenant_id=str(tenant.id),
        chunks=n,
        has_knowledge=n > 0,
    )
