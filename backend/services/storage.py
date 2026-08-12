import boto3
from botocore.client import Config
from config import settings


def get_s3_client():
    return boto3.client(
        "s3",
        endpoint_url=settings.STORAGE_ENDPOINT_URL,
        aws_access_key_id=settings.STORAGE_ACCESS_KEY,
        aws_secret_access_key=settings.STORAGE_SECRET_KEY,
        config=Config(signature_version="s3v4"),
    )


def upload_bytes(key: str, data: bytes, content_type: str = "image/png") -> str:
    client = get_s3_client()
    client.put_object(
        Bucket=settings.STORAGE_BUCKET_NAME,
        Key=key,
        Body=data,
        ContentType=content_type,
    )
    return key


def open_object(key: str, default_content_type: str = "image/png"):
    """
    Open an object for streaming. Returns (body, content_type).

    Every read goes through here so the storage backend lives in one file. The
    chart page endpoint used to call get_object() itself, which meant swapping
    S3 for anything else — Azure Blob, a mounted share — was a two-file change
    with one of them easy to miss.

    The body is a streaming handle, not bytes: chart pages are images and the
    endpoint hands them straight to a StreamingResponse rather than loading
    each one into memory.
    """
    client = get_s3_client()
    obj = client.get_object(Bucket=settings.STORAGE_BUCKET_NAME, Key=key)
    return obj["Body"], obj.get("ContentType", default_content_type)


def delete_object(key: str):
    client = get_s3_client()
    client.delete_object(Bucket=settings.STORAGE_BUCKET_NAME, Key=key)


def get_presigned_url(key: str, expires: int = 3600) -> str:
    client = get_s3_client()
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.STORAGE_BUCKET_NAME, "Key": key},
        ExpiresIn=expires,
    )
