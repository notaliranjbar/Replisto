from fastapi import HTTPException, UploadFile, status

from app.core.config import get_settings


async def read_upload(file: UploadFile) -> bytes:
    """Read an uploaded file, rejecting it once it exceeds the configured size limit."""
    limit = get_settings().upload_max_bytes
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE,
            f"The file is larger than {limit // (1024 * 1024)} MB.",
        )
    return data
