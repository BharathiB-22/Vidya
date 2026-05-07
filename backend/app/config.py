from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str
    REDIS_URL: str = "redis://localhost:6379/0"
    JWT_SECRET: str
    ENVIRONMENT: str = "development"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    OTP_EXPIRE_MINUTES: int = 10
    OTP_MAX_ATTEMPTS: int = 3
    BCRYPT_ROUNDS: int = 12

    # SMTP — leave SMTP_USER/SMTP_PASSWORD unset in dev to enable console mode
    SMTP_HOST: str = "localhost"
    SMTP_PORT: int = 587
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_FROM: str = "noreply@vidya.local"
    SMTP_TLS: bool = True
    EMAIL_NOTIFICATIONS_ENABLED: bool = True

    # Storage (S3-compatible via MinIO or AWS S3)
    S3_ENDPOINT: str = "http://localhost:9000"
    S3_ACCESS_KEY: str = "minioadmin"
    S3_SECRET_KEY: str = "minioadmin"
    S3_BUCKET: str = "vidya-assets"
    S3_REGION: str = "us-east-1"
    S3_USE_SSL: bool = False  # set True for prod
    MAX_UPLOAD_SIZE_MB: int = 50
    PRESIGNED_URL_EXPIRY_MINUTES_PUT: int = 15
    PRESIGNED_URL_EXPIRY_MINUTES_GET: int = 60
    STORAGE_ASSET_RETENTION_YEARS: int = 3

    # Storage MIME whitelist per entity type
    STORAGE_MIME_WHITELIST: dict = {
        "submission": [
            "application/pdf",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "image/jpeg",
            "image/png",
        ],
        "research_doc": [
            "application/pdf",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ],
        "viva_recording": ["video/mp4", "video/webm"],
        "course_kit": ["application/pdf"],
    }

    @property
    def SYNC_DATABASE_URL(self) -> str:
        return self.DATABASE_URL.replace("+asyncpg", "+psycopg2", 1)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
