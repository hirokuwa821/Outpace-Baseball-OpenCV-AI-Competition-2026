import os
import logging
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

# Configure a module‑level logger (no credentials are logged)
_logger = logging.getLogger(__name__)


def is_aws_configured() -> bool:
    """Return ``True`` if the required AWS environment variables are present.

    Currently the only variable required for S3 uploads is ``AWS_S3_BUCKET_NAME``.
    ``AWS_DEFAULT_REGION`` is optional – ``boto3`` will fall back to its default
    resolution chain.
    """
    return bool(os.getenv("AWS_S3_BUCKET_NAME"))


def get_s3_client():
    """Create and return a boto3 S3 client.

    If the AWS environment is not configured this function returns ``None``
    instead of raising an exception so that callers can safely fallback to the
    local workflow.
    """
    if not is_aws_configured():
        return None
    # boto3 automatically picks up credentials from environment variables,
    # ~/.aws/ credentials files, or an attached IAM role – we do not pass any
    # secret values explicitly.
    return boto3.client("s3")


def upload_file_to_s3(local_path: Path | str, s3_key: str) -> bool:
    """Upload a local file to an S3 bucket.

    Parameters
    ----------
    local_path: Path | str
        Path to the local file that should be uploaded.
    s3_key: str
        S3 object key (including any folder prefix) under which the file will be
        stored.

    Returns
    -------
    bool
        ``True`` if the upload succeeded, ``False`` otherwise.  When the AWS
        environment variables are missing the function simply returns ``False``
        without attempting any network call.
    """
    if not is_aws_configured():
        _logger.debug("AWS S3 configuration not found – skipping S3 upload.")
        return False

    bucket_name = os.getenv("AWS_S3_BUCKET_NAME")
    if not bucket_name:
        _logger.debug("AWS_S3_BUCKET_NAME is empty – skipping S3 upload.")
        return False

    try:
        s3 = get_s3_client()
        if s3 is None:
            _logger.debug("Failed to obtain S3 client – skipping upload.")
            return False

        # Ensure ``local_path`` is a string that boto3 can handle.
        file_path = str(local_path)
        s3.upload_file(file_path, bucket_name, s3_key)
        _logger.info("Uploaded %s to s3://%s/%s", file_path, bucket_name, s3_key)
        return True
    except ClientError as e:
        # Log the error without exposing any secret information.
        _logger.error("S3 upload failed for %s -> %s/%s: %s", local_path, bucket_name, s3_key, e)
        return False
    except Exception as e:
        # Catch‑all for unexpected errors (e.g., file not found).
        _logger.error("Unexpected error during S3 upload: %s", e)
        return False
