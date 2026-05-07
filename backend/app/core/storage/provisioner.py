import asyncio
import logging

import boto3
from botocore.exceptions import ClientError

from app.config import settings

logger = logging.getLogger("vidya.storage")


async def ensure_bucket_exists() -> None:
    """Create MinIO bucket if it doesn't exist.

    Called during app startup. Idempotent — safe to call multiple times.
    """
    loop = asyncio.get_event_loop()

    def _ensure():
        client = boto3.client(
            "s3",
            endpoint_url=settings.S3_ENDPOINT,
            aws_access_key_id=settings.S3_ACCESS_KEY,
            aws_secret_access_key=settings.S3_SECRET_KEY,
            region_name=settings.S3_REGION,
            use_ssl=settings.S3_USE_SSL,
        )

        try:
            client.head_bucket(Bucket=settings.S3_BUCKET)
            logger.info(f"S3 bucket '{settings.S3_BUCKET}' exists")
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                logger.info(f"Creating S3 bucket '{settings.S3_BUCKET}'")
                try:
                    client.create_bucket(Bucket=settings.S3_BUCKET)
                    logger.info(f"S3 bucket '{settings.S3_BUCKET}' created successfully")
                except ClientError as create_err:
                    # Handle race condition: another process created it
                    if create_err.response["Error"]["Code"] == "BucketAlreadyOwnedByYou":
                        logger.info(f"S3 bucket '{settings.S3_BUCKET}' already exists (concurrent creation)")
                    else:
                        raise
            else:
                raise

    await loop.run_in_executor(None, _ensure)
