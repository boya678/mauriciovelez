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
    AZURE_OPENAI_VOICE_DEPLOYMENT: str = ""
    AZURE_OPENAI_ENDPOINT_VOICE: str = ""
    AZURE_OPENAI_API_KEY_VOICE: str = ""
    AZURE_OPENAI_API_VERSION: str = "2024-02-01"
    # Empty string means: don't send the parameter (use model default).
    # Required for deployments like gpt-5-mini that only accept temperature=1.
    AZURE_OPENAI_TEMPERATURE: str = ""

    # Azure OpenAI — Embeddings
    AZURE_OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-large"
    AZURE_OPENAI_API_VERSION_EMBEDDING: str = "2024-02-01"

    # WhatsApp Meta Cloud API
    WHATSAPP_VERIFY_TOKEN: str = ""
    WHATSAPP_TOKEN: str = ""
    WHATSAPP_PHONE_ID: str = ""
    META_APP_SECRET: str = ""

    # AI tuning
    AI_MAX_TURNS: int = 10
    AI_CONFIDENCE_THRESHOLD: float = 0.6
    HUMAN_HANDOFF_NOTICE_TEXT: str = (
        "Voy a transferirte con un agente humano para continuar con tu solicitud. "
        "Un momento, por favor."
    )

    # Worker concurrency
    WORKER_POLL_INTERVAL_MS: int = 100
    WORKER_BLOCK_MS: int = 2000
    STREAM_CONSUMER_GROUP: str = "workers_group"
    AI_CONSUMER_GROUP: str = "ai_group"
    ASSIGN_CONSUMER_GROUP: str = "assignment_group"
    OUTGOING_CONSUMER_GROUP: str = "outgoing_group"
    OUTGOING_MAX_RETRIES: int = 5
    OUTGOING_RETRY_TTL_SECONDS: int = 3600
    OUTGOING_PROCESSING_LOCK_SECONDS: int = 120

    # Conversation inactivity lifecycle. Set ENABLED=false to disable it.
    # The close window starts only after the warning was delivered.
    CONVERSATION_IDLE_ENABLED: bool = True
    CONVERSATION_IDLE_WARNING_MINUTES: int = 30
    CONVERSATION_IDLE_GRACE_MINUTES: int = 10
    CONVERSATION_IDLE_SCAN_SECONDS: int = 60
    CONVERSATION_IDLE_SCAN_BATCH: int = 100
    CONVERSATION_IDLE_WARNING_TEXT: str = (
        "Seguimos atentos a tu respuesta. Si no recibimos un mensaje en los "
        "próximos {minutes} minutos, daremos por finalizada esta conversación."
    )
    CONVERSATION_IDLE_CLOSED_TEXT: str = (
        "Hemos finalizado esta conversación por inactividad. Cuando lo necesites, "
        "puedes escribirnos nuevamente y con gusto continuaremos ayudándote."
    )
    HUMAN_WAIT_TIMEOUT_MINUTES: int = 60
    HUMAN_WAIT_WINDOW_BUFFER_MINUTES: int = 5
    HUMAN_WAIT_TIMEOUT_TEXT: str = (
        "En este momento no fue posible conectarte con un agente. Hemos finalizado "
        "esta solicitud, pero puedes escribirnos nuevamente y con gusto te atenderemos."
    )
    CONVERSATION_EXPIRED_CLEANUP_MINUTES: int = 60
    MANUAL_CLOSE_NOTICE_TEXT: str = (
        "Hemos finalizado esta conversación. Cuando lo necesites, puedes escribirnos "
        "nuevamente y con gusto continuaremos ayudándote."
    )

    # App
    APP_ENV: str = "production"
    LOG_LEVEL: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
