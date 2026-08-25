from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.parametro import Parametro


@dataclass(frozen=True)
class NumeroRelampagoConfig:
    activo: bool
    valor: int
    numero: str


@dataclass(frozen=True)
class ConferenciaConfig:
    activo: bool
    valor: int
    fecha_aviso: str
    link_youtube: str


@dataclass(frozen=True)
class ConferenciaVipConfig:
    activo: bool
    valor: int
    fecha_aviso: str
    link_youtube: str


KEY_ACTIVO = "servicio_numero_relampago_activo"
KEY_VALOR = "servicio_numero_relampago_valor"
KEY_NUMERO = "servicio_numero_relampago_numero"

KEY_CONF_ACTIVO = "servicio_conferencia_activo"
KEY_CONF_VALOR = "servicio_conferencia_valor"
KEY_CONF_FECHA = "servicio_conferencia_fecha_aviso"
KEY_CONF_LINK = "servicio_conferencia_link_youtube"

KEY_CONF_VIP_ACTIVO = "servicio_conferencia_vip_activo"
KEY_CONF_VIP_VALOR = "servicio_conferencia_vip_valor"
KEY_CONF_VIP_FECHA = "servicio_conferencia_vip_fecha_aviso"
KEY_CONF_VIP_LINK = "servicio_conferencia_vip_link_youtube"


def _parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "si", "yes", "on"}


def _parse_int(value: str | None, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(value.strip())
    except Exception:
        return default


def get_numero_relampago_config(db: Session) -> NumeroRelampagoConfig:
    p_activo = db.get(Parametro, KEY_ACTIVO)
    p_valor = db.get(Parametro, KEY_VALOR)
    p_numero = db.get(Parametro, KEY_NUMERO)
    return NumeroRelampagoConfig(
        activo=_parse_bool(p_activo.valor if p_activo else None, default=False),
        valor=max(0, _parse_int(p_valor.valor if p_valor else None, default=0)),
        numero=(p_numero.valor.strip() if p_numero and p_numero.valor else ""),
    )


def set_numero_relampago_config(db: Session, activo: bool, valor: int, numero: str) -> NumeroRelampagoConfig:
    data = {
        KEY_ACTIVO: ("1" if activo else "0", "Servicio numero relampago activo (1/0)"),
        KEY_VALOR: (str(max(0, int(valor))), "Monto exacto para proceso numero relampago"),
        KEY_NUMERO: (numero.strip(), "Numero relampago a enviar en la notificacion"),
    }

    for key, (raw_val, desc) in data.items():
        p = db.get(Parametro, key)
        if p:
            p.valor = raw_val
            p.descripcion = desc
        else:
            db.add(Parametro(clave=key, valor=raw_val, descripcion=desc))

    db.flush()
    return NumeroRelampagoConfig(activo=activo, valor=max(0, int(valor)), numero=numero.strip())


def get_conferencia_config(db: Session) -> ConferenciaConfig:
    p_activo = db.get(Parametro, KEY_CONF_ACTIVO)
    p_valor = db.get(Parametro, KEY_CONF_VALOR)
    p_fecha = db.get(Parametro, KEY_CONF_FECHA)
    p_link = db.get(Parametro, KEY_CONF_LINK)
    return ConferenciaConfig(
        activo=_parse_bool(p_activo.valor if p_activo else None, default=False),
        valor=max(0, _parse_int(p_valor.valor if p_valor else None, default=0)),
        fecha_aviso=(p_fecha.valor.strip() if p_fecha and p_fecha.valor else ""),
        link_youtube=(p_link.valor.strip() if p_link and p_link.valor else ""),
    )


def set_conferencia_config(db: Session, activo: bool, valor: int, fecha_aviso: str, link_youtube: str) -> ConferenciaConfig:
    data = {
        KEY_CONF_ACTIVO: ("1" if activo else "0", "Servicio conferencia activo (1/0)"),
        KEY_CONF_VALOR: (str(max(0, int(valor))), "Monto exacto para proceso conferencia"),
        KEY_CONF_FECHA: (fecha_aviso.strip(), "Fecha/hora de conferencia para notificacion"),
        KEY_CONF_LINK: (link_youtube.strip(), "Link de YouTube para notificacion de conferencia"),
    }

    for key, (raw_val, desc) in data.items():
        p = db.get(Parametro, key)
        if p:
            p.valor = raw_val
            p.descripcion = desc
        else:
            db.add(Parametro(clave=key, valor=raw_val, descripcion=desc))

    db.flush()
    return ConferenciaConfig(
        activo=activo,
        valor=max(0, int(valor)),
        fecha_aviso=fecha_aviso.strip(),
        link_youtube=link_youtube.strip(),
    )


def get_conferencia_vip_config(db: Session) -> ConferenciaVipConfig:
    p_activo = db.get(Parametro, KEY_CONF_VIP_ACTIVO)
    p_valor = db.get(Parametro, KEY_CONF_VIP_VALOR)
    p_fecha = db.get(Parametro, KEY_CONF_VIP_FECHA)
    p_link = db.get(Parametro, KEY_CONF_VIP_LINK)
    return ConferenciaVipConfig(
        activo=_parse_bool(p_activo.valor if p_activo else None, default=False),
        valor=max(0, _parse_int(p_valor.valor if p_valor else None, default=0)),
        fecha_aviso=(p_fecha.valor.strip() if p_fecha and p_fecha.valor else ""),
        link_youtube=(p_link.valor.strip() if p_link and p_link.valor else ""),
    )


def set_conferencia_vip_config(db: Session, activo: bool, valor: int, fecha_aviso: str, link_youtube: str) -> ConferenciaVipConfig:
    data = {
        KEY_CONF_VIP_ACTIVO: ("1" if activo else "0", "Servicio conferencia VIP activo (1/0)"),
        KEY_CONF_VIP_VALOR: (str(max(0, int(valor))), "Monto exacto para proceso conferencia VIP"),
        KEY_CONF_VIP_FECHA: (fecha_aviso.strip(), "Fecha/hora de conferencia VIP para notificacion"),
        KEY_CONF_VIP_LINK: (link_youtube.strip(), "Link de YouTube para notificacion de conferencia VIP"),
    }

    for key, (raw_val, desc) in data.items():
        p = db.get(Parametro, key)
        if p:
            p.valor = raw_val
            p.descripcion = desc
        else:
            db.add(Parametro(clave=key, valor=raw_val, descripcion=desc))

    db.flush()
    return ConferenciaVipConfig(
        activo=activo,
        valor=max(0, int(valor)),
        fecha_aviso=fecha_aviso.strip(),
        link_youtube=link_youtube.strip(),
    )
