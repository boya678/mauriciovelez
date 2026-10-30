from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.parametro import Parametro


@dataclass(frozen=True)
class NumeroRelampagoConfig:
    activo: bool
    valor: int
    numero: str


@dataclass(frozen=True)
class VipConfig:
    activo: bool
    valor: int


@dataclass(frozen=True)
class RelampagoPersonalizadoConfig:
    activo: bool
    valor: int
    vigencia_dias: int
    rifa_activo: bool = False
    rifa_descripcion: str = ""


@dataclass(frozen=True)
class TablaNumerologicaConfig:
    activo: bool
    valor: int


@dataclass(frozen=True)
class RifaEnumeradaConfig:
    activo: bool
    valor: int
    cantidad: int


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

KEY_VIP_ACTIVO = "servicio_vip_activo"
KEY_VIP_VALOR = "servicio_vip_valor"

KEY_RP_ACTIVO = "servicio_relampago_personalizado_activo"
KEY_RP_VALOR = "servicio_relampago_personalizado_valor"
KEY_RP_VIGENCIA = "servicio_relampago_personalizado_vigencia_dias"
KEY_RP_RIFA_ACTIVO = "servicio_relampago_personalizado_rifa_activo"
KEY_RP_RIFA_DESC = "servicio_relampago_personalizado_rifa_descripcion"
KEY_RP_RIFA_SIGUIENTE = "servicio_relampago_personalizado_rifa_siguiente"

KEY_TN_ACTIVO = "servicio_tabla_numerologica_activo"
KEY_TN_VALOR = "servicio_tabla_numerologica_valor"

KEY_RE_ACTIVO = "servicio_rifa_enum_activo"
KEY_RE_VALOR = "servicio_rifa_enum_valor"
KEY_RE_CANTIDAD = "servicio_rifa_enum_cantidad"
KEY_RE_SIGUIENTE = "servicio_rifa_enum_siguiente"

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


def get_vip_config(db: Session) -> VipConfig:
    p_activo = db.get(Parametro, KEY_VIP_ACTIVO)
    p_valor = db.get(Parametro, KEY_VIP_VALOR)
    return VipConfig(
        activo=_parse_bool(p_activo.valor if p_activo else None, default=False),
        valor=max(0, _parse_int(p_valor.valor if p_valor else None, default=0)),
    )


def set_vip_config(db: Session, activo: bool, valor: int) -> VipConfig:
    data = {
        KEY_VIP_ACTIVO: ("1" if activo else "0", "Servicio VIP (monto alterno) activo (1/0)"),
        KEY_VIP_VALOR: (str(max(0, int(valor))), "Monto exacto alterno para renovacion/creacion VIP"),
    }

    for key, (raw_val, desc) in data.items():
        p = db.get(Parametro, key)
        if p:
            p.valor = raw_val
            p.descripcion = desc
        else:
            db.add(Parametro(clave=key, valor=raw_val, descripcion=desc))

    db.flush()
    return VipConfig(activo=activo, valor=max(0, int(valor)))


def get_relampago_personalizado_config(db: Session) -> RelampagoPersonalizadoConfig:
    p_activo = db.get(Parametro, KEY_RP_ACTIVO)
    p_valor = db.get(Parametro, KEY_RP_VALOR)
    p_vig = db.get(Parametro, KEY_RP_VIGENCIA)
    p_rifa_activo = db.get(Parametro, KEY_RP_RIFA_ACTIVO)
    p_rifa_desc = db.get(Parametro, KEY_RP_RIFA_DESC)
    return RelampagoPersonalizadoConfig(
        activo=_parse_bool(p_activo.valor if p_activo else None, default=False),
        valor=max(0, _parse_int(p_valor.valor if p_valor else None, default=0)),
        vigencia_dias=max(1, _parse_int(p_vig.valor if p_vig else None, default=1)),
        rifa_activo=_parse_bool(p_rifa_activo.valor if p_rifa_activo else None, default=False),
        rifa_descripcion=(p_rifa_desc.valor.strip() if p_rifa_desc and p_rifa_desc.valor else ""),
    )


def set_relampago_personalizado_config(
    db: Session, activo: bool, valor: int, vigencia_dias: int,
    rifa_activo: bool = False, rifa_descripcion: str = "",
) -> RelampagoPersonalizadoConfig:
    vigencia = max(1, int(vigencia_dias))
    descripcion = rifa_descripcion.strip()
    data = {
        KEY_RP_ACTIVO: ("1" if activo else "0", "Servicio numero relampago personalizado activo (1/0)"),
        KEY_RP_VALOR: (str(max(0, int(valor))), "Monto exacto que asigna un numero relampago personalizado"),
        KEY_RP_VIGENCIA: (str(vigencia), "Vigencia en dias del numero relampago personalizado"),
        KEY_RP_RIFA_ACTIVO: ("1" if rifa_activo else "0", "Asignar tambien numero de rifa 0000-9999 (1/0)"),
        KEY_RP_RIFA_DESC: (descripcion, "Descripcion del sorteo enviada en la notificacion del numero de rifa"),
    }

    for key, (raw_val, desc) in data.items():
        p = db.get(Parametro, key)
        if p:
            p.valor = raw_val
            p.descripcion = desc
        else:
            db.add(Parametro(clave=key, valor=raw_val, descripcion=desc))

    db.flush()
    return RelampagoPersonalizadoConfig(
        activo=activo, valor=max(0, int(valor)), vigencia_dias=vigencia,
        rifa_activo=rifa_activo, rifa_descripcion=descripcion,
    )


def get_tabla_numerologica_config(db: Session) -> TablaNumerologicaConfig:
    p_activo = db.get(Parametro, KEY_TN_ACTIVO)
    p_valor = db.get(Parametro, KEY_TN_VALOR)
    return TablaNumerologicaConfig(
        activo=_parse_bool(p_activo.valor if p_activo else None, default=False),
        valor=max(0, _parse_int(p_valor.valor if p_valor else None, default=0)),
    )


def set_tabla_numerologica_config(db: Session, activo: bool, valor: int) -> TablaNumerologicaConfig:
    data = {
        KEY_TN_ACTIVO: ("1" if activo else "0", "Servicio tabla numerologica activo (1/0)"),
        KEY_TN_VALOR: (str(max(0, int(valor))), "Monto exacto que envia la foto de la tabla numerologica"),
    }

    for key, (raw_val, desc) in data.items():
        p = db.get(Parametro, key)
        if p:
            p.valor = raw_val
            p.descripcion = desc
        else:
            db.add(Parametro(clave=key, valor=raw_val, descripcion=desc))

    db.flush()
    return TablaNumerologicaConfig(activo=activo, valor=max(0, int(valor)))


def get_rifa_enumerada_config(db: Session) -> RifaEnumeradaConfig:
    p_activo = db.get(Parametro, KEY_RE_ACTIVO)
    p_valor = db.get(Parametro, KEY_RE_VALOR)
    p_cantidad = db.get(Parametro, KEY_RE_CANTIDAD)
    return RifaEnumeradaConfig(
        activo=_parse_bool(p_activo.valor if p_activo else None, default=False),
        valor=max(0, _parse_int(p_valor.valor if p_valor else None, default=0)),
        cantidad=max(1, _parse_int(p_cantidad.valor if p_cantidad else None, default=1)),
    )


def set_rifa_enumerada_config(db: Session, activo: bool, valor: int, cantidad: int) -> RifaEnumeradaConfig:
    cantidad = max(1, int(cantidad))
    data = {
        KEY_RE_ACTIVO: ("1" if activo else "0", "Servicio rifa enumerada activo (1/0)"),
        KEY_RE_VALOR: (str(max(0, int(valor))), "Monto exacto que marca como pagadas las boletas de la rifa enumerada"),
        KEY_RE_CANTIDAD: (str(cantidad), "Boletas que se envian a cada celular en la rifa enumerada"),
    }

    for key, (raw_val, desc) in data.items():
        p = db.get(Parametro, key)
        if p:
            p.valor = raw_val
            p.descripcion = desc
        else:
            db.add(Parametro(clave=key, valor=raw_val, descripcion=desc))

    db.flush()
    return RifaEnumeradaConfig(activo=activo, valor=max(0, int(valor)), cantidad=cantidad)


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
