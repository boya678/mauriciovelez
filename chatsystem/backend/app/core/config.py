from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str  # postgresql+asyncpg://user:pass@host/db

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # JWT
    SECRET_KEY: str = ""          # alias kept for security.py
    JWT_SECRET_KEY: str = ""      # legacy alias
    ALGORITHM: str = "HS256"
    JWT_ALGORITHM: str = "HS256"  # legacy alias
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480

    # Azure OpenAI
    AZURE_OPENAI_ENDPOINT: str = ""
    AZURE_OPENAI_API_KEY: str = ""
    AZURE_OPENAI_DEPLOYMENT: str = "gpt-4o"
    AZURE_OPENAI_API_VERSION: str = "2024-02-01"

    # WhatsApp Meta Cloud API
    WHATSAPP_VERIFY_TOKEN: str = ""
    WHATSAPP_TOKEN: str = ""
    WHATSAPP_PHONE_ID: str = ""
    META_APP_SECRET: str = ""

    # AI tuning
    AI_MAX_TURNS: int = 10
    AI_CONFIDENCE_THRESHOLD: float = 0.6

    # Worker concurrency
    WORKER_POLL_INTERVAL_MS: int = 100
    WORKER_BLOCK_MS: int = 2000
    STREAM_CONSUMER_GROUP: str = "workers_group"
    AI_CONSUMER_GROUP: str = "ai_group"
    ASSIGN_CONSUMER_GROUP: str = "assignment_group"
    OUTGOING_CONSUMER_GROUP: str = "outgoing_group"

    # App
    APP_ENV: str = "production"
    LOG_LEVEL: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
