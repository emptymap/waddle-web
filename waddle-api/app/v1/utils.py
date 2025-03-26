from pathlib import Path
from typing import List

from fastapi import HTTPException, UploadFile, status
from sqlmodel import Session

from app.models import Episode, JobStatus

VARID_EXTENSIONS = [".wav", ".m4a", ".aifc", ".mp4"]
MAX_TOTAL_SIZE = 500 * 1024 * 1024  # 500MB limit


def get_episode_or_404(episode_id: str, session: Session) -> Episode:
    """Get an episode by ID or raise a 404 error if not found"""
    episode = session.get(Episode, episode_id)
    if not episode:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Episode not found")

    return episode


def validate_status_or_400(episode: Episode, status_field: str) -> None:
    """Check if a specific status is completed for an episode"""
    target_status = getattr(episode, status_field)
    if target_status != JobStatus.completed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Episode {status_field} is not completed. Current status: {target_status}")


def _get_combined_file(files: List[Path]) -> Path:
    """Get the combined file from a list of files"""
    combined_file = None
    for file in files:
        file_prefix = file.stem
        if "-" not in file_prefix:
            combined_file = file
            break
    if combined_file is None:
        combined_file = files[0]

    return combined_file


def get_post_combined_audio_or_404(episode_id: str, app_dir: Path) -> Path:
    """Get the combined audio file for an episode"""
    episode_dir = app_dir / "episodes" / episode_id
    audio_dir = episode_dir / "postprocessed"
    audio_files = list(audio_dir.glob("*.wav"))
    if not audio_files:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Edited audio file not found")

    return _get_combined_file(audio_files)


def get_combined_srt_or_404(episode_id: str, app_dir: Path) -> Path:
    """Get the combined SRT file for an episode"""
    episode_dir = app_dir / "episodes" / episode_id
    postprocessed_dir = episode_dir / "postprocessed"
    srt_files = list(postprocessed_dir.glob("*.srt"))
    if not srt_files:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SRT file not found")

    return _get_combined_file(srt_files)


def _is_safe_filename(filename: str) -> bool:
    """Check if a filename is safe to use (no path traversal characters or other unsafe patterns)."""
    if not filename or ".." in filename or "/" in filename or "\\" in filename:
        return False

    if filename.startswith("."):
        return False

    return True


async def validate_audio_files_or_400_413(files: list[UploadFile]) -> None:
    """Check if the uploaded files are audio files"""
    for file in files:
        if not file.filename:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No file name provided")
        if not _is_safe_filename(file.filename):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsafe file name")
        file_ext = Path(file.filename).suffix.lower()
        if file_ext not in VARID_EXTENSIONS:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported file type: {file_ext}")

    total_size = 0
    for file in files:
        # Try to get size from content-length header if available
        if "content-length" in file.headers:
            file_size = int(file.headers["content-length"])
            total_size += file_size
        else:
            chunk_size = 1024 * 1024  # 1MB chunks
            file_size = 0
            while True:
                chunk = await file.read(chunk_size)
                if not chunk:
                    break
                file_size += len(chunk)
                total_size += len(chunk)

                # Early exit if size exceeds limit
                if total_size > MAX_TOTAL_SIZE:
                    raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Total files size too large: 500MB limit")

            await file.seek(0)
