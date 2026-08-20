import os

MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "http://localhost:9000")
MINIO_ACCESS_KEY = os.environ.get(
    "MINIO_ACCESS_KEY",
    os.environ.get("MINIO_ROOT_USER", "admin"),
)
MINIO_SECRET_KEY = os.environ.get(
    "MINIO_SECRET_KEY",
    os.environ.get("MINIO_ROOT_PASSWORD", "minioadmin123"),
)
