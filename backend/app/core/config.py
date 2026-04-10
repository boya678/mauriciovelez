from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 180
    CLIENTE_DISABLED_MSG: str = "Tu cuenta no está habilitada. Comunícate con el equipo de Mauricio Vélez para más información."
    WHATSAPP_TOKEN: str = ""
    WHATSAPP_PHONE_ID: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
