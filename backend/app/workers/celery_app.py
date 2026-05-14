from kombu import Queue

from celery import Celery

from app.config import settings
from app.core.monitoring.celery_logging import setup_celery_logging

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
)

setup_celery_logging()
