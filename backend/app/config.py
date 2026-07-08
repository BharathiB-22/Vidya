from pathlib import Path
from typing import Literal

from cryptography.fernet import Fernet
from pydantic import model_validator
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

    # Google OAuth (for Super Admin Google Sign-In)
    GOOGLE_CLIENT_ID: str = ""

    # CORS
    # Comma-separated origins accepted by the API, e.g.
    # CORS_ALLOWED_ORIGINS=https://app.vidya.example,https://admin.vidya.example
    # Defaults to local dev ports so `npm run dev` works without extra config.
    CORS_ALLOWED_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:5173"]
    CORS_ALLOW_CREDENTIALS: bool = True

    # Trusted proxy IPs for X-Forwarded-For header processing.
    # "*" is safe when the app is behind ingress-nginx in Kubernetes and never
    # directly internet-accessible. Set to specific ingress pod CIDR in prod
    # if you want strict enforcement.
    TRUSTED_PROXY_IPS: str = "*"

    # AI provider selection: "gemini" | "groq" | "deepseek" | "fallback"
    # "fallback" tries Gemini → Groq → DeepSeek in order, stopping at first success.
    AI_PROVIDER: Literal["gemini", "groq", "deepseek", "fallback"] = "fallback"

    # Gemini AI
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.0-flash"
    AI_GEMINI_ENABLED: bool = True

    # Groq AI (OpenAI-compatible endpoint)
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.3-70b-versatile"
    AI_GROQ_ENABLED: bool = True

    # DeepSeek AI (OpenAI-compatible endpoint)
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_MODEL: str = "deepseek-chat"
    AI_DEEPSEEK_ENABLED: bool = True
    
    # Reference enrichment (M02)
    CROSSREF_BASE_URL: str = "https://api.crossref.org"
    OPENLIBRARY_BASE_URL: str = "https://openlibrary.org"
    REFERENCE_ENRICHMENT_MAX_PER_QUERY: int = 3
    REFERENCE_ENRICHMENT_TIMEOUT_SECONDS: float = 10.0

    # Course Kit Builder (M03)
    M03_MIN_SLIDES_PER_UNIT: int = 10
    M03_DEFAULT_COMPLEXITY: str = "UG"   # UG or PG; overridable per kit

    # Labs & Assignment Evaluator (M06)
    M06_AI_SCAN_THRESHOLD: float = 0.75       # flag if AI probability >= this
    M06_PLAGIARISM_THRESHOLD: float = 0.85    # flag if cosine similarity >= this
    M06_CODE_TIMEOUT_SECONDS: int = 10        # subprocess sandbox timeout
    M06_MAX_CODE_OUTPUT_CHARS: int = 4096     # truncate stdout/stderr beyond this

    # Research Supervision (M07)
    M07_WHISPER_ENDPOINT: str = ""              # blank = mock transcription in dev
    M07_MAX_VIVA_DURATION_MINS: int = 45
    M07_NOVELTY_SEARCH_MAX_RESULTS: int = 10
    M07_AI_CONTENT_THRESHOLD: float = 0.75
    M07_PLAGIARISM_THRESHOLD: float = 0.80
    M07_VIVA_SESSION_TTL_HOURS: int = 72
    M07_VIVA_RETENTION_YEARS: int = 3

    # Exam Setter (M08)
    # Fernet key (32 url-safe base64-encoded bytes) used to seal exam papers.
    # In dev: generate with Fernet.generate_key(). In prod: wrap via KMS.
    # NEVER store the actual key in DB — only encryption_key_ref is stored.
    EXAM_FERNET_KEY: str = ""                   # blank = auto-generate ephemeral key in dev
    M08_MIN_PAPER_SETS: int = 2                 # minimum number of question paper sets
    M08_BLOOM_COMPLIANCE_TOLERANCE: float = 5.0 # acceptable ± percent deviation per level
    M08_MAX_QUESTIONS_PER_PAPER: int = 50       # guard against runaway generation

    # Learning Material Packager (M05)
    YOUTUBE_API_KEY: str = ""
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_API_KEY: str = ""
    M05_TOP_N_PER_UNIT: int = 10
    M05_EMBED_BATCH_SIZE: int = 64
    M05_RAG_TOP_K: int = 5
    M05_RAG_CHUNK_TOKENS: int = 512
    M05_RAG_CHUNK_OVERLAP: int = 128
    M05_MIN_RELEVANCE_SCORE: float = 0.5  # items below this cosine similarity are rejected

    # Storage MIME whitelist per entity type
    STORAGE_MIME_WHITELIST: dict = {
        "submission": [
            "application/pdf",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/zip",
            "application/x-zip-compressed",
            "image/jpeg",
            "image/png",
        ],
        "research_doc": [
            "application/pdf",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ],
        "viva_recording": ["video/mp4", "video/webm"],
        "course_kit": [
            # Faculty-uploaded supporting resources (PDF/PPT/DOCX/reference notes).
            "application/pdf",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            "application/vnd.ms-powerpoint",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/msword",
            "text/plain",
        ],
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
        "scanned_script": [
            "application/pdf",
            "image/jpeg",
            "image/png",
        ],
        "faculty_note": [
            "application/pdf",
            "text/plain",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ],
        "avatar": [
            "image/jpeg",
            "image/png",
            "image/webp",
        ],
    }

    # Profile picture uploads are capped much tighter than the general
    # MAX_UPLOAD_SIZE_MB limit — enforced client-side and can be re-checked
    # server-side if a dedicated avatar validator is added later.
    AVATAR_MAX_UPLOAD_SIZE_MB: int = 5

    @property
    def SYNC_DATABASE_URL(self) -> str:
        url = self.DATABASE_URL.replace("+asyncpg", "+psycopg2", 1)
        # asyncpg uses ssl=disable; psycopg2 uses sslmode=disable
        return url.replace("ssl=disable", "sslmode=disable", 1)

    # ------------------------------------------------------------------
    # Startup guards
    # prod+staging: localhost DB/Redis, empty S3 credentials
    # production only: JWT quality, Fernet format, S3 defaults, TLS, CORS
    # Any violation raises ValueError immediately, preventing the app from
    # starting with insecure or broken configuration.
    # ------------------------------------------------------------------
    _KNOWN_DEV_JWT = (
        "1889a2bea7f4c026f5b6922687e67b4a72c47780076bf12c0233b8e1f9624cca"
    )
    _BAD_JWT_PATTERNS = ("dev-jwt", "change_me", "changeme", "secret", "test")

    @model_validator(mode="after")
    def _reject_insecure_production_config(self) -> "Settings":
        _is_prod = self.ENVIRONMENT == "production"
        _is_prod_like = self.ENVIRONMENT in ("production", "staging")

        if not _is_prod_like:
            return self

        errors: list[str] = []

        # ── production + staging ──────────────────────────────────────────
        if "@localhost" in self.DATABASE_URL or "@127.0.0.1" in self.DATABASE_URL:
            errors.append(
                "DATABASE_URL must not point to localhost in production or staging. "
                "Use your managed PostgreSQL endpoint."
            )

        if "@localhost" in self.REDIS_URL or "@127.0.0.1" in self.REDIS_URL:
            errors.append(
                "REDIS_URL must not point to localhost in production or staging. "
                "Use your managed Redis endpoint."
            )

        if not self.S3_ACCESS_KEY:
            errors.append(
                "S3_ACCESS_KEY must not be empty in production or staging environments."
            )

        if not self.S3_SECRET_KEY:
            errors.append(
                "S3_SECRET_KEY must not be empty in production or staging environments."
            )

        # ── production only ───────────────────────────────────────────────
        if _is_prod:
            if (
                self.JWT_SECRET == self._KNOWN_DEV_JWT
                or any(p in self.JWT_SECRET.lower() for p in self._BAD_JWT_PATTERNS)
            ):
                errors.append(
                    "JWT_SECRET is a known development or placeholder value. "
                    "Generate: openssl rand -hex 32"
                )
            elif len(self.JWT_SECRET) < 64:
                errors.append(
                    "JWT_SECRET must be at least 64 characters in production. "
                    "Generate: openssl rand -hex 32"
                )

            if not self.EXAM_FERNET_KEY:
                errors.append(
                    "EXAM_FERNET_KEY must be set in production — exam papers are "
                    "irrecoverable without it. Generate: "
                    "python -c \"from cryptography.fernet import Fernet; "
                    "print(Fernet.generate_key().decode())\""
                )
            else:
                try:
                    Fernet(self.EXAM_FERNET_KEY.encode())
                except Exception:
                    errors.append(
                        "EXAM_FERNET_KEY is not a valid Fernet key (must be 44-char "
                        "base64url ending in '='). Generate: "
                        "python -c \"from cryptography.fernet import Fernet; "
                        "print(Fernet.generate_key().decode())\""
                    )

            if self.S3_ACCESS_KEY == "minioadmin":
                errors.append(
                    "S3_ACCESS_KEY is set to the default 'minioadmin'. "
                    "Set a strong, unique credential before deploying."
                )

            if self.S3_SECRET_KEY == "minioadmin":
                errors.append(
                    "S3_SECRET_KEY is set to the default 'minioadmin'. "
                    "Set a strong, unique credential before deploying."
                )

            if not self.S3_USE_SSL:
                errors.append(
                    "S3_USE_SSL must be True in production. "
                    "Object storage must be accessed over TLS."
                )

            if not self.CORS_ALLOWED_ORIGINS:
                errors.append(
                    "CORS_ALLOWED_ORIGINS must not be empty in production. "
                    "Set the explicit origin(s) of your frontend deployment."
                )
            elif "*" in self.CORS_ALLOWED_ORIGINS:
                errors.append(
                    "CORS_ALLOWED_ORIGINS must not contain '*' in production. "
                    "Specify explicit origin(s)."
                )

        if errors:
            label = "Production" if _is_prod else "Staging"
            bullet_list = "\n".join(f"  • {e}" for e in errors)
            raise ValueError(
                f"{label} startup blocked — {len(errors)} insecure "
                f"configuration issue(s) detected:\n{bullet_list}"
            )

        return self

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
