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
    WHATSAPP_TEMPLATE_CODIGO: str = "codigo_cliente"
    WHATSAPP_VENCIMIENTO_VIP: str = "recordatorio_vencimiento_vip"
    WHATSAPP_CONTACTO_TRANSACCIONES: str = ""
    WHATSAPP_NOTIFICAR_RENOVACION: str = ""
    WHATSAPP_NOTIFICAR_RELAMPAGO: str = ""
    WHATSAPP_NOTIFICAR_CONFERENCIA: str = ""
    # Cron hora Colombia (minuto hora dom mes dow)
    CRON_NUMEROS: str = "0 8 * * *"        # reasignación de números 08:00 COL
    CRON_VIP_CHECK: str = "0 22 * * *"     # desactivar VIP vencidos 22:00 COL
    CRON_LOTERIAS: str = "0 10,14,18,23 * * *"  # procesar loterías (repetir a las horas indicadas COL)
    CRON_CONTACTOS: str = "0 22 * * *"     # sincroniza tags de contactos en DB2
    LOTERIAS_EVITAR: str = ""  # nombres separados por coma a ignorar en el cron
    REDIS_URL: str = "redis://redis:6379/0"
    REDIS_TTL: int = 14400  # segundos — tiempo de vida del historial de eventos live (4h)
    # Base de datos secundaria (chat)
    DATABASE_URL_2: str = ""
    DATABASE_SCHEMA_2: str = "t_mauriciovelez"
    # Azure OpenAI (vision para pagos automáticos)
    AZURE_OPENAI_ENDPOINT: str = ""
    AZURE_OPENAI_API_KEY: str = ""
    AZURE_OPENAI_DEPLOYMENT: str = "gpt-4.1-mini"
    AZURE_OPENAI_TEMPERATURE: float = 0.0
    VIP_AMOUNT: int = 30000
    CRON_PAGOS: str = "*/10 * * * *"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
