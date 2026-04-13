import io
import uuid

import openpyxl
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.admin_security import require_admin
from app.database import get_db
from app.models.contacto import Contacto
from app.models.cliente import Cliente

router = APIRouter(prefix="/admin/contactos", tags=["Admin Contactos"])


class ContactoOut(BaseModel):
    id: str
    cliente_id: str
    nombre: str
    celular: str
    numero: str
    loteria: str
    tipo_acierto: str
    fecha: str
    vip: bool

    model_config = {"from_attributes": True}


@router.get("", response_model=list[ContactoOut])
def list_contactos(
    db: Session = Depends(get_db),
    _user=Depends(require_admin),
):
    rows = (
        db.query(Contacto, Cliente)
        .join(Cliente, Contacto.cliente_id == Cliente.id)
        .order_by(Contacto.fecha.desc())
        .all()
    )
    return [
        ContactoOut(
            id=str(c.id),
            cliente_id=str(c.cliente_id),
            nombre=cl.nombre,
            celular=cl.celular,
            numero=c.numero,
            loteria=c.loteria,
            tipo_acierto=c.tipo_acierto,
            fecha=c.fecha.isoformat(),
            vip=cl.vip,
        )
        for c, cl in rows
    ]


@router.get("/export")
def export_contactos(
    db: Session = Depends(get_db),
    _user=Depends(require_admin),
):
    rows = (
        db.query(Contacto, Cliente)
        .join(Cliente, Contacto.cliente_id == Cliente.id)
        .order_by(Contacto.fecha.desc())
        .all()
    )

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Contactos"
    ws.append(["Fecha", "Nombre", "Celular", "Número", "Lotería", "Tipo", "VIP"])
    for c, cl in rows:
        ws.append([
            c.fecha.strftime("%d/%m/%Y %H:%M"),
            cl.nombre,
            cl.celular,
            c.numero,
            c.loteria,
            c.tipo_acierto,
            "Sí" if cl.vip else "No",
        ])

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=contactos.xlsx"},
    )


@router.delete("/{contacto_id}", status_code=204)
def delete_contacto(
    contacto_id: uuid.UUID,
    db: Session = Depends(get_db),
    _user=Depends(require_admin),
):
    row = db.query(Contacto).filter(Contacto.id == contacto_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Contacto no encontrado")
    db.delete(row)
    db.commit()
