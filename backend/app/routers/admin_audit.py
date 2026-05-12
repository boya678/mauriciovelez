from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.admin_security import require_admin
from app.database import get_db
from app.models.audit_log import AuditLog

router = APIRouter(prefix="/admin/audit", tags=["Admin Audit"])


class AuditOut(BaseModel):
    id: int
    usuario: str
    action: str
    entity: str
    entity_id: Optional[str]
    detail: Optional[dict]
    created_at: datetime

    model_config = {"from_attributes": True}


class PaginatedAudit(BaseModel):
    total: int
    page: int
    size: int
    items: list[AuditOut]


@router.get("", response_model=PaginatedAudit)
def list_audit(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    entity: Optional[str] = None,
    q: Optional[str] = Query(None, description="Búsqueda libre: usuario, acción, entidad, id"),
    db: Session = Depends(get_db),
    _user=Depends(require_admin),
):
    query = db.query(AuditLog)
    if entity:
        query = query.filter(AuditLog.entity == entity)
    if q:
        term = f"%{q.strip()}%"
        from sqlalchemy import cast, Text
        query = query.filter(
            AuditLog.usuario.ilike(term)
            | AuditLog.action.ilike(term)
            | AuditLog.entity.ilike(term)
            | AuditLog.entity_id.ilike(term)
            | cast(AuditLog.detail, Text).ilike(term)
        )
    total = query.count()
    items = (
        query.order_by(AuditLog.created_at.desc())
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )
    return PaginatedAudit(total=total, page=page, size=size, items=items)
