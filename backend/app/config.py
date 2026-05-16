from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve .env relative to this file so it is found regardless of CWD.
_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


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

    # Logging
    LOG_LEVEL: str = "INFO"
    JSON_LOGGING: bool = True
    HEALTH_CHECK_TIMEOUT_SECONDS: float = 2.0

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

    # AI provider selection: "groq" | "gemini" | "fallback"
    # "fallback" tries Gemini first and routes to Groq on quota errors.
    AI_PROVIDER: Literal["groq", "gemini", "fallback"] = "groq"

    # Gemini AI
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.0-flash"

    # Groq AI (OpenAI-compatible endpoint)
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.3-70b-versatile"
    
    # Reference enrichment (M02)
    CROSSREF_BASE_URL: str = "https://api.crossref.org"
    OPENLIBRARY_BASE_URL: str = "https://openlibrary.org"
    REFERENCE_ENRICHMENT_MAX_PER_QUERY: int = 3
    REFERENCE_ENRICHMENT_TIMEOUT_SECONDS: float = 10.0

    # Course Kit Builder (M03)
    M03_MIN_SLIDES_PER_UNIT: int = 8
    M03_MIN_QUIZLETS_PER_UNIT: int = 2
    M03_DEFAULT_COMPLEXITY: str = "UG"   # UG or PG; overridable per kit

    # Labs & Assignment Evaluator (M06)
    M06_AI_SCAN_THRESHOLD: float = 0.75       # flag if AI probability >= this
    M06_PLAGIARISM_THRESHOLD: float = 0.85    # flag if cosine similarity >= this
    M06_CODE_TIMEOUT_SECONDS: int = 10        # subprocess sandbox timeout
    M06_MAX_CODE_OUTPUT_CHARS: int = 4096     # truncate stdout/stderr beyond this

    # Learning Material Packager (M05)
    YOUTUBE_API_KEY: str = ""
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_API_KEY: str = ""
    M05_TOP_N_PER_UNIT: int = 10
    M05_EMBED_BATCH_SIZE: int = 64
    M05_RAG_TOP_K: int = 5
    M05_RAG_CHUNK_TOKENS: int = 512
    M05_RAG_CHUNK_OVERLAP: int = 128

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
        "program_export": [
            "application/pdf",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ],
        "syllabus_export": [
            "application/pdf",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/json",
        ],
        "course_kit_export": [
            "application/pdf",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ],
    }

    @property
    def SYNC_DATABASE_URL(self) -> str:
        return self.DATABASE_URL.replace("+asyncpg", "+psycopg2", 1)

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
