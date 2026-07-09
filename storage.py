import boto3

from config import settings

BUCKET = settings.aws_s3_bucket_name

# Credentials passed explicitly from settings — no reliance on boto3's implicit env lookup.
_s3 = boto3.client(
    "s3",
    endpoint_url=settings.aws_endpoint_url,
    region_name=settings.aws_default_region,
    aws_access_key_id=settings.aws_access_key_id,
    aws_secret_access_key=settings.aws_secret_access_key,
)


def upload(key: str, data: bytes, content_type: str) -> str:
    _s3.put_object(Bucket=BUCKET, Key=key, Body=data, ContentType=content_type)
    return key


def delete(key: str) -> None:
    _s3.delete_object(Bucket=BUCKET, Key=key)


def presigned_url(key: str, expires: int = 3600) -> str:
    # Bucket serves the bytes directly with Range support — no proxying through the API.
    return _s3.generate_presigned_url(
        "get_object", Params={"Bucket": BUCKET, "Key": key}, ExpiresIn=expires
    )
