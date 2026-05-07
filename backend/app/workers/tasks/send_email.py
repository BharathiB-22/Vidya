import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.workers.celery_app import celery_app
from app.workers.base_task import VidyaTask

logger = logging.getLogger("vidya.email")


@celery_app.task(
    base=VidyaTask,
    name="app.workers.tasks.send_email",
    autoretry_for=(smtplib.SMTPException, ConnectionError, TimeoutError, OSError),
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=120,
    retry_jitter=True,
)
def send_email(
    *,
    recipient_email: str,
    subject: str,
    body_text: str,
    body_html: str | None = None,
    **kwargs,   # absorbs any extra kwargs (e.g. forwarded context fields)
) -> dict:
    """Deliver a single email via SMTP.

    No job_id is passed — VidyaTask hooks no-op cleanly.
    In dev mode (SMTP_USER unset) the message is printed to stdout
    so developers see it without a real mail server.
    """
    from app.config import settings

    if not settings.SMTP_USER:
        _dev_log(recipient_email, subject, body_text)
        return {"sent": False, "mode": "dev"}

    msg = _build_message(
        from_addr=settings.SMTP_FROM,
        to_addr=recipient_email,
        subject=subject,
        body_text=body_text,
        body_html=body_html,
    )

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as conn:
        if settings.SMTP_TLS:
            conn.starttls()
        conn.login(settings.SMTP_USER, settings.SMTP_PASSWORD or "")
        conn.sendmail(settings.SMTP_FROM, [recipient_email], msg.as_string())

    logger.info("email_sent to=%s subject=%r", recipient_email, subject)
    return {"sent": True, "recipient": recipient_email}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_message(
    *,
    from_addr: str,
    to_addr: str,
    subject: str,
    body_text: str,
    body_html: str | None,
) -> MIMEMultipart:
    msg = MIMEMultipart("alternative")
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.attach(MIMEText(body_text, "plain"))
    if body_html:
        msg.attach(MIMEText(body_html, "html"))
    return msg


def _dev_log(recipient_email: str, subject: str, body_text: str) -> None:
    print(
        f"[DEV] EMAIL to={recipient_email} subject={subject!r}\n{body_text}",
        flush=True,
    )
