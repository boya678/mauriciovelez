from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 180
    CLIENTE_DISABLED_MSG: str = "Tu cuenta no está habilitada. Comunícate con el equipo de Mauricio Vélez para más información."
    WHATSAPP_TOKEN: str = ""
    WHATSAPP_PHONE_ID: str = ""
    WHATSAPP_TEMPLATE_GANADOR_FREE: str = "ganador_free"
    WHATSAPP_TEMPLATE_GANADOR_VIP: str = "vip_ganador"
    WHATSAPP_TEMPLATE_NOTIFICACION_NUMERO_VIP: str = "vip_nuevo_numero"
    WHATSAPP_TEMPLATE_NOTIFICACION_NUMERO_FREE: str = "free_nuevo_numero"
    WHATSAPP_TEMPLATE_OTP: str = "codigo_otp"
    WHATSAPP_TEMPLATE_NOTIFICACION_REFERIDO: str = "free_referido"
    # Cron hora Colombia (minuto hora dom mes dow)
    CRON_NUMEROS: str = "0 8 * * *"        # reasignación de números 08:00 COL
    CRON_VIP_CHECK: str = "0 22 * * *"     # desactivar VIP vencidos 22:00 COL
    CRON_LOTERIAS: str = "0 10,14,18,23 * * *"  # procesar loterías (repetir a las horas indicadas COL)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
