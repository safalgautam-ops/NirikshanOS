"""
Actual Python code that does the talking to MinIO. This file is where the
app reads and writes files.

To talk to MinIO, the app uses a ready-made toolkit called aioboto3
aiboto3 is the library that knows how to format the requests, sign them, send them, and read the replies.
aioboto3 is the version of Amazon's official toolkit (boto3) built for async code
It works on MinIO because MinIO deliberately speaks the same language as Aamazon S3.

The two things involved: Session and Client
The Session holds who you are;
the Client is an active conversation with the storage server.

An aioboto3 client wraps a single network connection and
isn't safe to share across many simultaneous requests.

Here's the problem. A web app handles many users at the same time.
Imagine 50 people all uploading at once.
If they all tried to shout down one single shared phone line,
you'd get chaos — their messages would collide and tangle,
because that one connection wasn't built to carry 50 conversations at once.
So keeping one client open and sharing it everywhere is risky —
it can break under concurrent use.
The fix is the opposite extreme: each task gets its own private phone call.
Person A's upload opens its own line, does its thing, hangs up.
Person B's upload, happening at the same time, opens a separate line.
No collisions, because no two tasks ever share a connection. This is safe.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import aioboto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError

from app.config import Config

# the app creates the session once when it starts up and keeps it forever. (just holding the settings)
_session = aioboto3.Session()


# a small helper function that bundles up the connection settings: which address to use,
# plus the username/password from your config file. endpoint_url is a parameter since
# the app needs two different addresses:
# one for the app talking to MinIO itself
# one for when a link is being made that the browser will use
# s3v4 is the modern signing standard MinIO expects.
def _client_kwargs(endpoint_url: str) -> dict:
    return {
        "endpoint_url": endpoint_url,
        "aws_access_key_id": Config.MINIO_ACCESS_KEY,
        "aws_secret_access_key": Config.MINIO_SECRET_KEY,
        "config": BotoConfig(signature_version="s3v4"),
    }


# normal client used for internal app itself doing: uploading, deleting, listing
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
    """A client configured with the browser-reachable endpoint, used only
    for generate_presigned_url - the endpoint a client is configured with
    is exactly the host that ends up baked into the signed URL, and
    MINIO_ENDPOINT (the container-network hostname "minio") is never
    reachable from a browser. Never opens a real connection - presigning is
    a local computation, not a network call."""
    async with _session.client(
        "s3", **_client_kwargs(Config.MINIO_PRESIGN_ENDPOINT)
    ) as client:
        yield client


async def bootstrap_buckets() -> None:
    """
    For each bucket, it checks existence (head_bucket) and
    creates it if missing. This is the bootstrap_buckets()
    mentioned way back in the Docker file — the app's own way of guaranteeing
    the buckets exist, so even if you delete the minio-init helper or
    wipe the data volume, the app fixes itself on startup.
    """
    async with get_client() as client:
        for bucket in (Config.MINIO_BUCKET_PUBLIC, Config.MINIO_BUCKET_PRIVATE):
            try:
                await client.head_bucket(Bucket=bucket)
            except ClientError:
                await client.create_bucket(Bucket=bucket)

        # Anonymous-read on the public bucket only - lets nginx's /media/
        # location proxy straight through to MinIO with no auth, the same
        # way /static/ serves files directly off disk today.
        # applies to the public bucket only: Principal * means anyone,
        # s3:GetObject means can read files.
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
        await client.put_bucket_policy(
            Bucket=Config.MINIO_BUCKET_PUBLIC, Policy=json.dumps(policy)
        )
        # Note: MinIO doesn't implement the S3 PutBucketCors API (it 404s/
        # NotImplemented-s) - CORS for evidence parts being PUT straight
        # from the browser to a presigned MinIO URL is instead configured
        # server-wide via `mc admin config set local api cors_allow_origin=...`,
        # which defaults to "*" out of the box. See _browser_origin() if
        # that default is ever locked down and this needs revisiting.


"""
simple read write helpers -- each opens a normal client and does one operation.
A key is just the file's path/name inside the bucket (like avatars/user42.png
"""


async def put_object(bucket: str, key: str, data: bytes, content_type: str) -> None:
    async with get_client() as client:
        await client.put_object(
            Bucket=bucket, Key=key, Body=data, ContentType=content_type
        )  # do the one job for the actual operation and close the connection automatically


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
    """A short-lived(900s --> 15 minutes), signed download link - the only way anything in the
    private bucket (documents/evidence) is ever read back, since that
    bucket has no anonymous access at all."""
    async with get_presign_client() as client:
        return await client.generate_presigned_url(
            "get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=expires_in
        )


def public_url(key: str) -> str:
    """Stable, unsigned URL for an object in the public (anonymous-read)
    bucket - nothing to presign, nothing to expire. Since no work, no async used."""
    return f"{Config.MINIO_PUBLIC_URL}/{key}"


"""
MULTIPART UPLOAD SECTION -- for giant evidence files
sending 100 GB in one HTTP request, so S3 lets you split a file into parts, upload them seperately (even in parallel), then stitch back them together.
"""


async def create_multipart_upload(bucket: str, key: str, content_type: str) -> str:
    async with get_client() as client:
        result = await client.create_multipart_upload(
            Bucket=bucket, Key=key, ContentType=content_type
        )
        return result["UploadId"]  # UploadId tags all the pieces as beloging together


async def presigned_part_url(
    bucket: str, key: str, upload_id: str, part_number: int, expires_in: int = 900
) -> str:
    """A presigned PUT for one part - the browser sends the part's bytes
    straight to MinIO with this, the app never sees them. This is what
    makes parallel part upload possible: the client can hold several of
    these in flight via separate XHRs at once."""
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
    """Which parts MinIO actually has for this upload - the ground truth
    both progress display and resume are built on (see
    app/features/evidence/service.py.get_upload_state)."""
    parts: list[dict] = []
    async with get_client() as client:
        paginator = client.get_paginator("list_parts")
        async for page in paginator.paginate(
            Bucket=bucket, Key=key, UploadId=upload_id
        ):
            for part in page.get("Parts", []):
                parts.append(
                    {
                        "part_number": part["PartNumber"],
                        "size": part["Size"],  # which parts it has actually received
                        "etag": part["ETag"],  # fingerprint of each part
                    }
                )
    return parts


async def complete_multipart_upload(bucket: str, key: str, upload_id: str) -> int:
    """Completes the upload using the parts MinIO itself reports via
    list_parts - never trusts a client-supplied part/ETag list. Returns
    the completed object's total size in bytes."""
    parts = await list_parts(bucket, key, upload_id)
    if not parts:
        raise ValueError("No parts have been uploaded.")
    ordered = sorted(parts, key=lambda p: p["part_number"])
    multipart_parts = [
        {"PartNumber": p["part_number"], "ETag": p["etag"]} for p in ordered
    ]
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


async def stream_object(bucket: str, key: str, chunk_size: int = 4 * 1024 * 1024):
    """Async generator yielding the object's bytes in chunks - used by the
    post-upload background hashing task (see evidence/service.py) to
    compute sha256/md5 without loading a multi-GB file into memory."""
    async with get_client() as client:
        response = await client.get_object(Bucket=bucket, Key=key)
        stream = response["Body"]
        while True:
            chunk = await stream.read(chunk_size)
            if not chunk:
                break
            yield chunk
