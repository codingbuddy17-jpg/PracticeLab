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
