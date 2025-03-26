import shutil
import zipfile
from pathlib import Path
from typing import Annotated, List

from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from platformdirs import user_data_dir
from sqlmodel import Session, select
from waddle.metadata import generate_metadata
from waddle.processing.combine import combine_audio_files
from waddle.processor import postprocess_multi_files, preprocess_multi_files

from app.db import get_session
from app.defaults import APP_AUTHOR, APP_NAME
from app.models import AnnotatedSrtContent, Episode, JobStatus, JobType, ProcessingJob, UpdateEpisodeRequest

SessionDep = Annotated[Session, Depends(get_session)]
app_dir = Path(user_data_dir(APP_NAME, APP_AUTHOR))

# Create v1 router
v1_router = APIRouter(tags=["v1"])


#####################################
# MARK: Episode CRUD operations
#####################################
episodes_router = APIRouter(tags=["episodes"])


@episodes_router.get("/episodes/", response_model=List[Episode])
def read_episodes(
    session: SessionDep,
    offset: Annotated[int, Query(ge=0, description="Offset the number of episodes returned")] = 0,
    limit: Annotated[int, Query(le=100, description="Limit the number of episodes returned")] = 100,
) -> List[Episode]:
    """Read all episodes"""
    episodes = session.exec(select(Episode).offset(offset).limit(limit)).all()
    return list(episodes)


@episodes_router.post(
    "/episodes/",
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_400_BAD_REQUEST: {"description": "No file name provided"},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"description": "Internal server error"},
    },
)
async def create_episode(
    files: list[UploadFile], session: SessionDep, background_tasks: BackgroundTasks, title: Annotated[str, Form(description="Episode title")] = ""
) -> Episode:
    new_episode = Episode(title=title, preprocess_status=JobStatus.pending)
    session.add(new_episode)
    session.commit()
    session.refresh(new_episode)

    storage_path = app_dir / "episodes" / new_episode.uuid
    storage_path.mkdir(parents=True, exist_ok=True)

    source_dir = storage_path / "source"
    source_dir.mkdir(exist_ok=True)
    try:
        for file in files:
            if not file.filename:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No file name provided")
            file_path = source_dir / file.filename
            with open(file_path, "wb") as f:
                content = await file.read()
                f.write(content)
        session.add(new_episode)
        job = ProcessingJob(episode_id=new_episode.uuid, type=JobType.preprocess, status=JobStatus.pending)
        session.add(job)
        session.commit()

        background_tasks.add_task(run_preprocessing, job.id, new_episode.uuid, session)
        return new_episode
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)) from e


# Background preprocessing task
def run_preprocessing(job_id: int, episode_uuid: str, session: SessionDep) -> None:
    job = session.get(ProcessingJob, job_id)
    if not job:
        return
    episode = session.get(Episode, episode_uuid)
    if not episode:
        return
    episode.preprocess_status = JobStatus.processing
    job.status = JobStatus.processing
    session.commit()
    session.refresh(episode)
    session.refresh(job)
    try:
        episode_dir = app_dir / "episodes" / episode_uuid
        preprocess_multi_files(reference=None, source_dir=episode_dir / "source", output_dir=episode_dir / "preprocessed", transcribe=True)
        episode.preprocess_status = JobStatus.completed
        job.status = JobStatus.completed
    except Exception as e:
        episode.preprocess_status = JobStatus.failed
        job.status = JobStatus.failed
        job.error_message = str(e)
    finally:
        session.commit()
        session.refresh(episode)
        session.refresh(job)
        session.close()


def _get_episode_or_404(episode_id: str, session: Session) -> Episode:
    episode = session.get(Episode, episode_id)
    if not episode:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Episode not found")
    return episode


@episodes_router.get(
    "/episodes/{episode_id}",
    response_model=Episode,
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "Episode not found"},
    },
)
def get_episode(episode_id: str, session: SessionDep) -> Episode:
    """Get a specific episode by ID"""
    return _get_episode_or_404(episode_id, session)


@episodes_router.patch(
    "/episodes/{episode_id}",
    response_model=Episode,
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "Episode not found"},
    },
)
def update_episode(episode_id: str, update_data: UpdateEpisodeRequest, session: SessionDep) -> Episode:
    """Update an existing episode"""
    episode = _get_episode_or_404(episode_id, session)

    if update_data.title is not None:
        episode.title = update_data.title
    if update_data.editor_state is not None:
        episode.editor_state = update_data.editor_state

    session.add(episode)
    session.commit()
    session.refresh(episode)
    return episode


@episodes_router.delete(
    "/episodes/{episode_id}", status_code=status.HTTP_204_NO_CONTENT, responses={status.HTTP_404_NOT_FOUND: {"description": "Episode not found"}}
)
def delete_episode(episode_id: str, session: SessionDep) -> None:
    """Delete an episode"""
    episode = _get_episode_or_404(episode_id, session)
    session.delete(episode)
    session.commit()

    episode_dir = app_dir / "episodes" / episode_id
    if episode_dir.exists():
        shutil.rmtree(episode_dir)

    return None  # Using 204 No Content for successful deletion


#####################################
# MARK: Preprocessed resources: audio files and SRT transcription
#####################################
preprocess_resources_router = APIRouter(tags=["preprocessed_resources"])


def _check_preprocessed_or_400(episode: Episode) -> None:
    """Check if preprocessing is completed for an episode"""
    if episode.preprocess_status != JobStatus.completed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Episode preprocessing is not completed. Current status: {episode.preprocess_status}"
        )


@preprocess_resources_router.get("/episodes/{episode_id}/audios", response_model=List[str])
def get_preprocessed_audio_files(episode_id: str, session: SessionDep) -> List[str]:
    """Retrieves all preprocessed audio filenames for a specific episode"""
    episode = _get_episode_or_404(episode_id, session)
    _check_preprocessed_or_400(episode)

    preprocessed_dir = app_dir / "episodes" / episode_id / "preprocessed"
    if not preprocessed_dir.exists():
        return []

    audio_files: List[str] = []
    for file_path in preprocessed_dir.glob("*.wav"):
        audio_files.append(file_path.name)
    return audio_files


@preprocess_resources_router.get(
    "/episodes/{episode_id}/audio/{file_name}",
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "Audio file or episode not found"},
        status.HTTP_400_BAD_REQUEST: {"description": "Episode preprocessing not completed"},
    },
)
def get_audio_file(episode_id: str, file_name: str, session: SessionDep) -> FileResponse:
    """Retrieves a specific audio file"""
    episode = _get_episode_or_404(episode_id, session)
    _check_preprocessed_or_400(episode)

    # Validate and sanitize file_name to prevent directory traversal
    if ".." in file_name or "/" in file_name or "\\" in file_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid file name")

    audio_file_path = app_dir / "episodes" / episode_id / "preprocessed" / file_name
    if not audio_file_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audio file not found")

    return FileResponse(path=audio_file_path, media_type="audio/wav", filename=audio_file_path.name)


@preprocess_resources_router.get(
    "/episodes/{episode_id}/srt",
    response_model=str,
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "SRT file or episode not found"},
        status.HTTP_400_BAD_REQUEST: {"description": "Episode preprocessing not completed"},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"description": "Error reading SRT file"},
    },
)
def get_transcription(episode_id: str, session: SessionDep) -> str:
    """Retrieves SRT transcription file content as a string"""
    episode = _get_episode_or_404(episode_id, session)
    _check_preprocessed_or_400(episode)

    preprocessed_dir = app_dir / "episodes" / episode_id / "preprocessed"
    srt_files = list(preprocessed_dir.glob("*.srt"))
    if not srt_files:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SRT file not found")

    srt_file_path = srt_files[0]

    try:
        with open(srt_file_path, "r", encoding="utf-8") as file:
            srt_content = file.read()
        return srt_content
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error reading SRT file: {str(e)}") from e


#####################################
# MARK: Audio editing endpoints
# TODO: Implement audio editing endpoints
#####################################
audio_editing_router = APIRouter(tags=["audio_editing"])


def _check_edited_or_400(episode: Episode) -> None:
    """Check if audio editing is completed for an episode"""
    if episode.edit_status != JobStatus.completed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Episode audio editing is not completed. Current status: {episode.edit_status}")


@audio_editing_router.post(
    "/episodes/{episode_id}/audio-edits",
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "Episode not found"},
        status.HTTP_400_BAD_REQUEST: {"description": "Episode preprocessing not completed"},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"description": "Internal server error"},
    },
)
def apply_audio_edits(episode_id: str, session: SessionDep, background_tasks: BackgroundTasks) -> Episode:
    """Apply audio edits based on the episode's editor_state"""
    episode = _get_episode_or_404(episode_id, session)
    _check_preprocessed_or_400(episode)

    job = ProcessingJob(episode_id=episode.uuid, type=JobType.edit, status=JobStatus.pending)
    session.add(job)

    episode.edit_status = JobStatus.pending
    session.add(episode)

    session.commit()
    session.refresh(job)
    session.refresh(episode)

    background_tasks.add_task(run_editing, job_id=job.id, episode_uuid=episode_id, session=session)

    return episode


def run_editing(job_id: int, episode_uuid: str, session: SessionDep) -> None:
    """Background task to run audio editing"""
    job = session.get(ProcessingJob, job_id)
    if not job:
        return

    episode = session.get(Episode, episode_uuid)
    if not episode:
        return

    episode.edit_status = JobStatus.processing
    job.status = JobStatus.processing
    session.commit()
    session.refresh(episode)
    session.refresh(job)

    try:
        episode_dir = app_dir / "episodes" / episode_uuid
        source_dir = episode_dir / "preprocessed"
        edited_dir = episode_dir / "edited"
        edited_dir.mkdir(exist_ok=True, parents=True)

        # Copy all preprocessed audio files to edited directory
        for file_path in source_dir.glob("*.wav"):
            shutil.copy(file_path, edited_dir)

        # Get all audio files
        edited_files = sorted(list(edited_dir.glob("*.wav")))
        if not edited_files:
            raise Exception("No audio files found")

        # Create combined audio file from edits
        combine_audio_path = episode_dir / "edited-combined.wav"
        combine_audio_files(edited_files, combine_audio_path)

        episode.edit_status = JobStatus.completed
        job.status = JobStatus.completed
    except Exception as e:
        episode.edit_status = JobStatus.failed
        job.status = JobStatus.failed
        job.error_message = str(e)
    finally:
        session.commit()
        session.refresh(episode)
        session.refresh(job)
        session.close()


@audio_editing_router.get(
    "/episodes/{episode_id}/edited-audio",
)
def get_edited_audio_files(episode_id: str, session: SessionDep) -> FileResponse:
    """Get the final edited audio file"""
    episode = _get_episode_or_404(episode_id, session)
    _check_edited_or_400(episode)

    episode_dir = app_dir / "episodes" / episode_id
    edited_combine_path = episode_dir / "edited-combined.wav"
    if not edited_combine_path.exists():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Edit audio is not completed")

    return FileResponse(path=edited_combine_path, media_type="audio/wav", filename=edited_combine_path.name)


#####################################
# MARK: Post-processing endpoints
#####################################
postprocess_router = APIRouter(tags=["postprocess"])


def _check_postprocessed_or_400(episode: Episode) -> None:
    """Check if post-processing is completed for an episode"""
    if episode.postprocess_status != JobStatus.completed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Episode post-processing is not completed. Current status: {episode.postprocess_status}"
        )


@postprocess_router.post(
    "/episodes/{episode_id}/postprocess",
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "Episode not found"},
        status.HTTP_400_BAD_REQUEST: {"description": "Episode preprocessing not completed"},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"description": "Internal server error"},
    },
)
def initiate_postprocess(episode_id: str, background_tasks: BackgroundTasks, session: SessionDep) -> Episode:
    """Initiate post-processing for an episode using its current editor state"""
    episode = _get_episode_or_404(episode_id, session)
    _check_edited_or_400(episode)

    job = ProcessingJob(episode_id=episode.uuid, type=JobType.postprocess, status=JobStatus.pending)
    session.add(job)
    session.commit()
    session.refresh(job)

    background_tasks.add_task(run_postprocessing, job_id=job.id, episode_uuid=episode_id, session=session)

    episode.postprocess_status = JobStatus.pending
    session.add(episode)
    session.commit()
    session.refresh(episode)

    return episode


def run_postprocessing(job_id: int, episode_uuid: str, session: SessionDep) -> None:
    """Background task to run post-processing"""
    job = session.get(ProcessingJob, job_id)
    if not job:
        return

    episode = session.get(Episode, episode_uuid)
    if not episode:
        return

    episode.postprocess_status = JobStatus.processing
    job.status = JobStatus.processing
    session.commit()
    session.refresh(episode)
    session.refresh(job)

    try:
        episode_dir = app_dir / "episodes" / episode_uuid
        source_dir = episode_dir / "edited"
        output_dir = episode_dir / "postprocessed"
        output_dir.mkdir(exist_ok=True, parents=True)

        postprocess_multi_files(source_dir=source_dir, output_dir=output_dir)

        episode.postprocess_status = JobStatus.completed
        job.status = JobStatus.completed
    except Exception as e:
        episode.postprocess_status = JobStatus.failed
        job.status = JobStatus.failed
        job.error_message = str(e)
    finally:
        session.commit()
        session.refresh(episode)
        session.refresh(job)
        session.close()


@postprocess_router.get(
    "/episodes/{episode_id}/postprocessed-audio",
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "Post-processed audio not found or episode not found"},
        status.HTTP_400_BAD_REQUEST: {"description": "Post-processing not completed"},
    },
)
def get_postprocessed_audio(episode_id: str, session: SessionDep) -> FileResponse:
    """Get the final post-processed audio file"""
    episode = _get_episode_or_404(episode_id, session)
    _check_postprocessed_or_400(episode)

    # Check if post-processing is completed
    if episode.postprocess_status != JobStatus.completed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Episode post-processing is not completed. Current status: {episode.postprocess_status}"
        )

    postprocessed_dir = app_dir / "episodes" / episode_id / "postprocessed"
    if not postprocessed_dir.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post-processed directory not found")

    # Look for audio files (assuming .wav format)
    audio_files = list(postprocessed_dir.glob("*.wav"))
    if not audio_files:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post-processed audio file not found")

    combined_audio = None
    for audio_file in audio_files:
        audio_prefix = audio_file.stem
        if "-" not in audio_prefix:
            combined_audio = audio_file
            break
    if combined_audio is None:
        combined_audio = audio_files[0]

    return FileResponse(path=combined_audio, media_type="audio/wav", filename=combined_audio.name)


#####################################
# MARK: Transcription Management endpoints
#####################################
transcription_router = APIRouter(tags=["transcription"])


def _get_combined_srt_or_404(episode_id: str) -> Path:
    """Get the combined SRT file for an episode"""
    episode_dir = app_dir / "episodes" / episode_id
    postprocessed_dir = episode_dir / "postprocessed"
    srt_files = list(postprocessed_dir.glob("*.srt"))
    if not srt_files:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SRT file not found")

    combined_srt = None
    for srt_file in srt_files:
        srt_prefix = srt_file.stem
        if "-" not in srt_prefix:
            combined_srt = srt_file
            break
    if combined_srt is None:
        combined_srt = srt_files[0]

    return combined_srt


@transcription_router.get(
    "/episodes/{episode_id}/annotated-srt",
    response_model=AnnotatedSrtContent,
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "Episode or annotated SRT file not found"},
        status.HTTP_400_BAD_REQUEST: {"description": "Episode preprocessing not completed"},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"description": "Error reading annotated SRT file"},
    },
)
def get_annotated_srt(episode_id: str, session: SessionDep) -> AnnotatedSrtContent:
    """Retrieves annotated SRT with speaker information"""
    episode = _get_episode_or_404(episode_id, session)
    _check_postprocessed_or_400(episode)

    preprocessed_dir = app_dir / "episodes" / episode_id / "postprocessed"
    srt_files = list(preprocessed_dir.glob("*.srt"))
    if not srt_files:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Annotated SRT file not found")
    combined_srt = _get_combined_srt_or_404(episode_id)

    try:
        with open(combined_srt, "r", encoding="utf-8") as file:
            srt_content = file.read()
        return AnnotatedSrtContent(content=srt_content)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error reading annotated SRT file: {str(e)}") from e


@transcription_router.put(
    "/episodes/{episode_id}/annotated-srt",
    response_model=AnnotatedSrtContent,
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "Episode not found"},
        status.HTTP_400_BAD_REQUEST: {"description": "Episode preprocessing not completed"},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"description": "Error writing annotated SRT file"},
    },
)
def update_annotated_srt(episode_id: str, annotated_srt: AnnotatedSrtContent, session: SessionDep) -> AnnotatedSrtContent:
    """Updates annotated SRT with speaker information"""
    episode = _get_episode_or_404(episode_id, session)
    _check_postprocessed_or_400(episode)

    preprocessed_dir = app_dir / "episodes" / episode_id / "postprocessed"
    srt_files = list(preprocessed_dir.glob("*.srt"))
    if not srt_files:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Annotated SRT file not found")
    combined_srt = _get_combined_srt_or_404(episode_id)

    try:
        with open(combined_srt, "w", encoding="utf-8") as file:
            file.write(annotated_srt.content)
        return annotated_srt
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error writing annotated SRT file: {str(e)}") from e


#####################################
# MARK: Metadata Generation endpoints
#####################################
metadata_router = APIRouter(tags=["metadata"])


def _check_metadata_or_400(episode: Episode) -> None:
    """Check if metadata generation is completed for an episode"""
    if episode.metadata_generation_status != JobStatus.completed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Episode metadata generation is not completed. Current status: {episode.metadata_generation_status}",
        )


@metadata_router.post(
    "/episodes/{episode_id}/metadata",
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "Episode not found"},
        status.HTTP_400_BAD_REQUEST: {"description": "Episode preprocessing not completed"},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"description": "Internal server error"},
    },
)
def generate_episode_metadata(episode_id: str, session: SessionDep) -> list[str]:
    """
    Generate metadata for an episode including chapters and show notes based on the annotated SRT file.
    """
    episode = _get_episode_or_404(episode_id, session)
    _check_postprocessed_or_400(episode)

    episode.metadata_generation_status = JobStatus.processing
    session.commit()
    session.refresh(episode)

    episode_dir: Path = app_dir / "episodes" / episode_id
    metadata_dir = episode_dir / "metadata"
    metadata_dir.mkdir(exist_ok=True, parents=True)

    srt_file = _get_combined_srt_or_404(episode_id)

    postprocessed_dir = episode_dir / "postprocessed"
    audio_files = list(postprocessed_dir.glob("*.wav"))

    audio_file = None
    if audio_files:
        combined_audio = None
        for audio in audio_files:
            audio_prefix = audio.stem
            if "-" not in audio_prefix:
                combined_audio = audio
                break
        audio_file = combined_audio or audio_files[0]

    # Generate metadata
    try:
        generate_metadata(source_file=srt_file, audio_file=audio_file, output_dir=metadata_dir)
        episode.metadata_generation_status = JobStatus.completed
    except Exception as e:
        episode.metadata_generation_status = JobStatus.failed
        episode.error_message = str(e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error generating metadata: {str(e)}") from e
    finally:
        session.commit()
        session.refresh(episode)

    generated_paths = list(metadata_dir.glob("*"))
    return [generated_path.name for generated_path in generated_paths]


@metadata_router.get(
    "/episodes/{episode_id}/metadata-audio",
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "Episode or audio file not found"},
        status.HTTP_400_BAD_REQUEST: {"description": "Metadata generation not completed"},
    },
)
def get_metadata_audio(episode_id: str, session: SessionDep) -> FileResponse:
    """Get the audio file for an episode"""
    episode = _get_episode_or_404(episode_id, session)
    _check_metadata_or_400(episode)

    metadata_dir = app_dir / "episodes" / episode_id / "metadata"
    if not metadata_dir.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Metadata directory not found")

    audio_files = list(metadata_dir.glob("*.wav"))
    if not audio_files:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audio file not found")

    audio_file = audio_files[0]
    return FileResponse(path=audio_file, media_type="audio/wav", filename=audio_file.name)


@metadata_router.get(
    "/episodes/{episode_id}/chapters",
    response_model=str,
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "Episode or chapters file not found"},
        status.HTTP_400_BAD_REQUEST: {"description": "Metadata generation not completed"},
    },
)
def get_chapter_info(episode_id: str, session: SessionDep) -> str:
    """Get chapter information for an episode"""
    episode = _get_episode_or_404(episode_id, session)
    _check_metadata_or_400(episode)

    metadata_dir = app_dir / "episodes" / episode_id / "metadata"
    if not metadata_dir.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Metadata directory not found")

    chapter_files = list(metadata_dir.glob("*.chapters.txt"))
    if not chapter_files:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chapter file not found")

    chapter_file = chapter_files[0]
    try:
        with open(chapter_file, "r", encoding="utf-8") as file:
            chapters_content = file.read()
        return chapters_content
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error reading chapter file: {str(e)}") from e


@metadata_router.get(
    "/episodes/{episode_id}/show-notes",
    response_model=str,
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "Episode or show notes file not found"},
        status.HTTP_400_BAD_REQUEST: {"description": "Metadata generation not completed"},
    },
)
def get_show_notes(episode_id: str, session: SessionDep) -> str:
    """Get show notes for an episode"""
    episode = _get_episode_or_404(episode_id, session)
    _check_metadata_or_400(episode)

    metadata_dir = app_dir / "episodes" / episode_id / "metadata"
    if not metadata_dir.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Metadata directory not found")

    show_notes_files = list(metadata_dir.glob("*.show_notes.md"))
    if not show_notes_files:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Show notes file not found")

    show_notes_file = show_notes_files[0]
    try:
        with open(show_notes_file, "r", encoding="utf-8") as file:
            show_notes_content = file.read()
        return show_notes_content
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error reading show notes file: {str(e)}") from e


#####################################
# MARK: Export endpoints
#####################################
export_router = APIRouter(tags=["export"])


def _check_export_or_400(episode: Episode) -> None:
    """Check if export is completed for an episode"""
    if episode.export_status != JobStatus.completed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Episode export is not completed. Current status: {episode.export_status}")


@export_router.post(
    "/episodes/{episode_id}/export",
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "Episode not found"},
        status.HTTP_400_BAD_REQUEST: {"description": "Episode post-processing not completed"},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"description": "Internal server error"},
    },
)
def initiate_export(episode_id: str, background_tasks: BackgroundTasks, session: SessionDep) -> Episode:
    """Initiate export of processed episode files"""
    episode = _get_episode_or_404(episode_id, session)
    _check_metadata_or_400(episode)

    job = ProcessingJob(episode_id=episode.uuid, type=JobType.export, status=JobStatus.pending)
    session.add(job)
    session.commit()
    session.refresh(job)

    background_tasks.add_task(run_export, job_id=job.id, episode_uuid=episode_id, session=session)

    episode.export_status = JobStatus.pending
    session.add(episode)
    session.commit()
    session.refresh(episode)

    return episode


def run_export(job_id: int, episode_uuid: str, session: SessionDep) -> None:
    """Background task to run export compression"""
    job = session.get(ProcessingJob, job_id)
    if not job:
        return

    episode = session.get(Episode, episode_uuid)
    if not episode:
        return

    episode.export_status = JobStatus.processing
    job.status = JobStatus.processing
    session.commit()
    session.refresh(episode)
    session.refresh(job)

    try:
        episode_dir = app_dir / "episodes" / episode_uuid
        export_dir = episode_dir / "export"
        if export_dir.exists():
            # Remove existing export directory, for if title changes
            shutil.rmtree(export_dir)
        export_dir.mkdir(parents=True)
        zip_path = export_dir / f"{episode.title or 'episode'}.zip"

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            metadata_dir = episode_dir / "metadata"
            if metadata_dir.exists():
                for file_path in metadata_dir.glob("*.*"):
                    zipf.write(file_path, arcname=file_path.name)

            srt_file = _get_combined_srt_or_404(episode_uuid)
            if srt_file.exists():
                zipf.write(srt_file, arcname=srt_file.name)

        episode.export_status = JobStatus.completed
        job.status = JobStatus.completed
    except Exception as e:
        episode.export_status = JobStatus.failed
        job.status = JobStatus.failed
        job.error_message = str(e)
    finally:
        session.commit()
        session.refresh(episode)
        session.refresh(job)
        session.close()


@export_router.get(
    "/episodes/{episode_id}/export",
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "Export not found or episode not found"},
        status.HTTP_400_BAD_REQUEST: {"description": "Export not completed"},
    },
)
def download_export(episode_id: str, session: SessionDep) -> FileResponse:
    """Download the exported zip file for an episode"""
    episode = _get_episode_or_404(episode_id, session)
    _check_export_or_400(episode)

    export_dir = app_dir / "episodes" / episode_id / "export"
    if not export_dir.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export directory not found")

    zip_files = list(export_dir.glob("*.zip"))
    if not zip_files:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export zip file not found")

    zip_file = zip_files[0]  # Get the first zip file (there should only be one)
    return FileResponse(
        path=zip_file, media_type="application/zip", filename=zip_file.name, headers={"Content-Disposition": f"attachment; filename={zip_file.name}"}
    )


#####################################
# MARK: Include routers
#####################################
v1_router.include_router(episodes_router)
v1_router.include_router(preprocess_resources_router)
v1_router.include_router(audio_editing_router)
v1_router.include_router(postprocess_router)
v1_router.include_router(transcription_router)
v1_router.include_router(metadata_router)
v1_router.include_router(export_router)
