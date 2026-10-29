import asyncio
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile, status

from app.core.config import settings

IMAGE_CAPTION_MAX_LENGTH = 4000
IMAGE_SUBDIR = "images"

_UNSUPPORTED_IMAGE_DETAIL = "Unsupported image format. Allowed: JPEG, PNG, GIF, WEBP"
_TOO_LARGE_IMAGE_DETAIL = "Image is too large"
_EMPTY_IMAGE_DETAIL = "Image file is empty"


@dataclass(frozen=True)
class StoredImage:
    filename: str
    url: str
    mime_type: str
    size_bytes: int


def detect_image_format(data: bytes) -> tuple[str, str] | None:
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", ".jpg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", ".png"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif", ".gif"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp", ".webp"
    return None


def normalize_caption(caption: str | None) -> str:
    if caption is None:
        return ""
    caption = caption.strip()
    if len(caption) > IMAGE_CAPTION_MAX_LENGTH:
        raise HTTPException(
            status_code=422,
            detail=f"Caption must be at most {IMAGE_CAPTION_MAX_LENGTH} characters",
        )
    return caption


class ImageStorage:
    def __init__(
        self,
        upload_dir: str | None = None,
        url_prefix: str | None = None,
        max_size_bytes: int | None = None,
    ) -> None:
        self.upload_dir = Path(upload_dir if upload_dir is not None else settings.upload_dir)
        self.url_prefix = (
            url_prefix if url_prefix is not None else settings.media_url_prefix
        ).rstrip("/")
        self.max_size_bytes = (
            max_size_bytes if max_size_bytes is not None else settings.max_image_size_bytes
        )
        self.images_dir = self.upload_dir / IMAGE_SUBDIR

    async def save(self, upload: UploadFile) -> StoredImage:
        data = await upload.read(self.max_size_bytes + 1)
        if not data:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_EMPTY_IMAGE_DETAIL)
        if len(data) > self.max_size_bytes:
            raise HTTPException(status_code=413, detail=_TOO_LARGE_IMAGE_DETAIL)

        detected = detect_image_format(data)
        if detected is None:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=_UNSUPPORTED_IMAGE_DETAIL,
            )

        mime_type, extension = detected
        filename = f"{uuid4().hex}{extension}"
        await asyncio.to_thread(self._write_file, self.images_dir / filename, data)
        return StoredImage(
            filename=filename,
            url=f"{self.url_prefix}/{IMAGE_SUBDIR}/{filename}",
            mime_type=mime_type,
            size_bytes=len(data),
        )

    async def delete(self, stored: StoredImage) -> None:
        await asyncio.to_thread((self.images_dir / stored.filename).unlink, missing_ok=True)

    def _write_file(self, path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
