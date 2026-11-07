import asyncio
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile, status

from app.core.config import settings

AUDIO_SUBDIR = "audio"
VIDEO_NOTE_SUBDIR = "video_notes"

MIN_DURATION_SECONDS = 1
MAX_DURATION_SECONDS = 3600

_AUDIO_UNSUPPORTED_DETAIL = "Unsupported audio format. Allowed: OGG, MP3, WAV, M4A, WEBM"
_AUDIO_TOO_LARGE_DETAIL = "Audio file is too large"
_AUDIO_EMPTY_DETAIL = "Audio file is empty"

_VIDEO_NOTE_UNSUPPORTED_DETAIL = "Unsupported video note format. Allowed: MP4, WEBM"
_VIDEO_NOTE_TOO_LARGE_DETAIL = "Video note is too large"
_VIDEO_NOTE_EMPTY_DETAIL = "Video note file is empty"


@dataclass(frozen=True)
class StoredMedia:
    filename: str
    url: str
    mime_type: str
    size_bytes: int


def detect_audio_format(data: bytes) -> tuple[str, str] | None:
    if data.startswith(b"OggS"):
        return "audio/ogg", ".ogg"
    if data.startswith(b"ID3") or (len(data) >= 2 and data[0] == 0xFF and data[1] & 0xE0 == 0xE0):
        return "audio/mpeg", ".mp3"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return "audio/wav", ".wav"
    if len(data) >= 12 and data[4:8] == b"ftyp":
        return "audio/mp4", ".m4a"
    if data.startswith(b"\x1aE\xdf\xa3"):
        return "audio/webm", ".webm"
    return None


def detect_video_note_format(data: bytes) -> tuple[str, str] | None:
    if len(data) >= 12 and data[4:8] == b"ftyp":
        return "video/mp4", ".mp4"
    if data.startswith(b"\x1aE\xdf\xa3"):
        return "video/webm", ".webm"
    return None


def normalize_duration(value: float | None) -> int | None:
    if value is None:
        return None
    duration = round(value)
    if duration < MIN_DURATION_SECONDS or duration > MAX_DURATION_SECONDS:
        raise HTTPException(
            status_code=422,
            detail=(
                f"duration_seconds must be between {MIN_DURATION_SECONDS} and "
                f"{MAX_DURATION_SECONDS}"
            ),
        )
    return duration


class _MediaStorage:
    subdir: str
    supported_detail: str
    too_large_detail: str
    empty_detail: str

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
            max_size_bytes if max_size_bytes is not None else self.default_max_size_bytes()
        )
        self.media_dir = self.upload_dir / self.subdir

    def default_max_size_bytes(self) -> int:
        raise NotImplementedError

    def detect(self, data: bytes) -> tuple[str, str] | None:
        raise NotImplementedError

    async def save(self, upload: UploadFile) -> StoredMedia:
        data = await upload.read(self.max_size_bytes + 1)
        if not data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=self.empty_detail
            )
        if len(data) > self.max_size_bytes:
            raise HTTPException(status_code=413, detail=self.too_large_detail)

        detected = self.detect(data)
        if detected is None:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=self.supported_detail,
            )

        mime_type, extension = detected
        filename = f"{uuid4().hex}{extension}"
        await asyncio.to_thread(self._write_file, self.media_dir / filename, data)
        return StoredMedia(
            filename=filename,
            url=f"{self.url_prefix}/{self.subdir}/{filename}",
            mime_type=mime_type,
            size_bytes=len(data),
        )

    async def delete(self, stored: StoredMedia) -> None:
        await asyncio.to_thread((self.media_dir / stored.filename).unlink, missing_ok=True)

    def _write_file(self, path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


class AudioStorage(_MediaStorage):
    subdir = AUDIO_SUBDIR
    supported_detail = _AUDIO_UNSUPPORTED_DETAIL
    too_large_detail = _AUDIO_TOO_LARGE_DETAIL
    empty_detail = _AUDIO_EMPTY_DETAIL

    def default_max_size_bytes(self) -> int:
        return settings.max_audio_size_bytes

    def detect(self, data: bytes) -> tuple[str, str] | None:
        return detect_audio_format(data)


class VideoNoteStorage(_MediaStorage):
    subdir = VIDEO_NOTE_SUBDIR
    supported_detail = _VIDEO_NOTE_UNSUPPORTED_DETAIL
    too_large_detail = _VIDEO_NOTE_TOO_LARGE_DETAIL
    empty_detail = _VIDEO_NOTE_EMPTY_DETAIL

    def default_max_size_bytes(self) -> int:
        return settings.max_video_note_size_bytes

    def detect(self, data: bytes) -> tuple[str, str] | None:
        return detect_video_note_format(data)
