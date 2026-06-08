from kombu import Queue

from celery import Celery

from app.config import settings
from app.core.monitoring.celery_logging import setup_celery_logging
import app.models  # noqa: F401 — register all ORM models in Base.metadata before tasks run

celery_app = Celery(
    "vidya",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "app.workers.tasks.send_email",
        "app.workers.heavy.program_structure",
        "app.workers.heavy.program_export",
        "app.workers.heavy.syllabus_generation",
        "app.workers.heavy.reference_enrichment",
        "app.workers.heavy.syllabus_export",
        "app.workers.heavy.course_kit_generation",
        "app.workers.heavy.course_kit_export",
        "app.workers.heavy.curate_learning_package",
        "app.workers.heavy.index_package_rag",
        "app.workers.heavy.evaluate_lab_submission",
        "app.workers.heavy.evaluate_research_proposal",
        "app.workers.heavy.evaluate_research_document",
        "app.workers.heavy.process_viva_session",
        "app.workers.heavy.generate_exam_paper",
        "app.workers.heavy.regenerate_exam_question",
        "app.workers.heavy.release_exam_paper",
        "app.workers.heavy.detect_scan_quality",
        "app.workers.heavy.ocr_scanned_script",
        "app.workers.heavy.score_scanned_script",
        "app.workers.heavy.stale_task_cleanup",
        "app.workers.heavy.analyse_score_distribution",
        "app.workers.heavy.generate_transcript_pdf",
    ],
)

celery_app.conf.update(
    # Serialisation
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",

    # Time
    timezone="UTC",
    enable_utc=True,

    # Results are kept for 24 h then purged
    result_expires=86_400,

    # Queues
    task_queues=(
        Queue("celery"),           # light tasks: notifications, email, webhooks
        Queue("celery-heavy"),     # heavy tasks: AI generation (Gemini), PDF builds
    ),
    task_default_queue="celery",

    # Routing — tasks registered under app.workers.heavy.* go to celery-heavy.
    # All other tasks default to celery.
    task_routes={
        "app.workers.heavy.*": {"queue": "celery-heavy"},
    },

    # Reliability
    task_acks_late=True,           # ack after task body completes, not on pickup
    worker_prefetch_multiplier=1,  # fair dispatch; prevents heavy tasks being hoarded

    # Beat — periodic tasks
    beat_schedule={
        "stale-task-cleanup": {
            "task": "app.workers.heavy.stale_task_cleanup",
            "schedule": 300.0,  # every 5 minutes
        },
    },
)

setup_celery_logging()
