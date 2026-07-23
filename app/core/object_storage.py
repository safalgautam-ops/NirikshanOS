"""Actual Python code that does the talking to MinIO."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import aioboto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError

from app.config import Config

_session = aioboto3.Session()


def _client_kwargs(endpoint_url: str) -> dict:
    return {
        "endpoint_url": endpoint_url,
        "aws_access_key_id": Config.MINIO_ACCESS_KEY,
        "aws_secret_access_key": Config.MINIO_SECRET_KEY,
        "config": BotoConfig(signature_version="s3v4"),
    }


"""
The @asynccontextmanager + async with + yield pattern is just the clean way
to say: "open a client, hand it over for use, and guarantee it gets closed
afterward even if something errors."
"""


@asynccontextmanager
async def get_client() -> AsyncIterator[Any]:
    async with _session.client("s3", **_client_kwargs(Config.MINIO_ENDPOINT)) as client:
        yield client


@asynccontextmanager
async def get_presign_client() -> AsyncIterator[Any]:
    """A client configured with the browser-reachable endpoint, used only for generate_presigned_url - the endpoint a client is configured with is exactly the host that ends up baked into the signed URL, and MINIO_ENDPOINT (the container-network hostname "minio") is never reachable from a browser."""
    async with _session.client("s3", **_client_kwargs(Config.MINIO_PRESIGN_ENDPOINT)) as client:
        yield client


async def bootstrap_buckets() -> None:
    """For each bucket, it checks existence (head_bucket) and creates it if missing."""
    async with get_client() as client:
        for bucket in (Config.MINIO_BUCKET_PUBLIC, Config.MINIO_BUCKET_PRIVATE):
            try:
                await client.head_bucket(Bucket=bucket)
            except ClientError:
                await client.create_bucket(Bucket=bucket)

        policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": "*",
                    "Action": ["s3:GetObject"],
                    "Resource": [f"arn:aws:s3:::{Config.MINIO_BUCKET_PUBLIC}/*"],
                }
            ],
        }
        await client.put_bucket_policy(Bucket=Config.MINIO_BUCKET_PUBLIC, Policy=json.dumps(policy))


"""
simple read write helpers -- each opens a normal client and does one operation.
A key is just the file's path/name inside the bucket (like avatars/user42.png
"""


async def put_object(bucket: str, key: str, data: bytes, content_type: str) -> None:
    async with get_client() as client:
        await client.put_object(Bucket=bucket, Key=key, Body=data, ContentType=content_type)


async def delete_object(bucket: str, key: str) -> None:
    async with get_client() as client:
        await client.delete_object(Bucket=bucket, Key=key)


async def object_exists(bucket: str, key: str) -> bool:
    async with get_client() as client:
        try:
            await client.head_object(Bucket=bucket, Key=key)
            return True
        except ClientError:
            return False


async def presigned_get_url(bucket: str, key: str, expires_in: int = 900) -> str:
    """A short-lived(900s --> 15 minutes), signed download link - the only way anything in the private bucket (documents/evidence) is ever read back, since that bucket has no anonymous access at all."""
    async with get_presign_client() as client:
        return await client.generate_presigned_url(
            "get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=expires_in
        )


def public_url(key: str) -> str:
    """Stable, unsigned URL for an object in the public (anonymous-read) bucket - nothing to presign, nothing to expire."""
    return f"{Config.MINIO_PUBLIC_URL}/{key}"


"""
MULTIPART UPLOAD SECTION -- for giant evidence files
sending 100 GB in one HTTP request, so S3 lets you split a file into parts, upload them seperately (even in parallel), then stitch back them together.
"""


async def create_multipart_upload(bucket: str, key: str, content_type: str) -> str:
    async with get_client() as client:
        result = await client.create_multipart_upload(Bucket=bucket, Key=key, ContentType=content_type)
        return result["UploadId"]


async def presigned_part_url(
    bucket: str, key: str, upload_id: str, part_number: int, expires_in: int = 900
) -> str:
    """A presigned PUT for one part - the browser sends the part's bytes straight to MinIO with this, the app never sees them."""
    async with get_presign_client() as client:
        return await client.generate_presigned_url(
            "upload_part",
            Params={
                "Bucket": bucket,
                "Key": key,
                "UploadId": upload_id,
                "PartNumber": part_number,
            },
            ExpiresIn=expires_in,
        )


async def list_parts(bucket: str, key: str, upload_id: str) -> list[dict]:
    """Which parts MinIO actually has for this upload - the ground truth both progress display and resume are built on (see app/features/evidence/service.py.get_upload_state)."""
    parts: list[dict] = []
    async with get_client() as client:
        paginator = client.get_paginator("list_parts")
        async for page in paginator.paginate(Bucket=bucket, Key=key, UploadId=upload_id):
            for part in page.get("Parts", []):
                parts.append(
                    {
                        "part_number": part["PartNumber"],
                        "size": part["Size"],
                        "etag": part["ETag"],
                    }
                )
    return parts


async def complete_multipart_upload(bucket: str, key: str, upload_id: str) -> int:
    """Completes the upload using the parts MinIO itself reports via list_parts - never trusts a client-supplied part/ETag list."""
    parts = await list_parts(bucket, key, upload_id)
    if not parts:
        raise ValueError("No parts have been uploaded.")
    ordered = sorted(parts, key=lambda p: p["part_number"])
    multipart_parts = [{"PartNumber": p["part_number"], "ETag": p["etag"]} for p in ordered]
    async with get_client() as client:
        await client.complete_multipart_upload(
            Bucket=bucket,
            Key=key,
            UploadId=upload_id,
            MultipartUpload={"Parts": multipart_parts},
        )
    return sum(p["size"] for p in parts)


async def abort_multipart_upload(bucket: str, key: str, upload_id: str) -> None:
    async with get_client() as client:
        await client.abort_multipart_upload(Bucket=bucket, Key=key, UploadId=upload_id)


async def download_object(bucket: str, key: str, local_path: str) -> None:
    """Download an object from MinIO to a local file path."""
    from pathlib import Path

    dest = Path(local_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    async with get_client() as client:
        response = await client.get_object(Bucket=bucket, Key=key)
        stream = response["Body"]
        with dest.open("wb") as f:
            while True:
                chunk = await stream.read(8 * 1024 * 1024)
                if not chunk:
                    break
                f.write(chunk)


async def stream_object(bucket: str, key: str, chunk_size: int = 4 * 1024 * 1024):
    """Async generator yielding the object's bytes in chunks - used by the post-upload background hashing task (see evidence/service.py) to compute sha256/md5 without loading a multi-GB file into memory."""
    async with get_client() as client:
        response = await client.get_object(Bucket=bucket, Key=key)
        stream = response["Body"]
        while True:
            chunk = await stream.read(chunk_size)
            if not chunk:
                break
            yield chunk
