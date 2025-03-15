from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Annotated, List

from fastapi import BackgroundTasks, Depends, FastAPI, Query, UploadFile
from platformdirs import user_data_dir
from sqlmodel import Session, select

from app.db import create_db_and_tables, get_session
from app.defaults import APP_AUTHOR, APP_NAME
from app.models import Episode, JobStatus, JobType, ProcessingJob

SessionDep = Annotated[Session, Depends(get_session)]

app_dir = Path(user_data_dir(APP_NAME, APP_AUTHOR))


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    yield


app = FastAPI(lifespan=lifespan)


# Episode CRUD endpoints
@app.get("/episodes/", response_model=List[Episode])
def read_episodes(
    session: SessionDep,
    offset: Annotated[int, Query(ge=0, description="Offset the number of episodes returned")] = 0,
    limit: Annotated[int, Query(le=100, description="Limit the number of episodes returned")] = 100,
):
    """Read all episodes"""
    episodes = session.exec(select(Episode).offset(offset).limit(limit)).all()
    return episodes


@app.post("/episodes/")
async def create_episode(files: list[UploadFile], background_tasks: BackgroundTasks, db: SessionDep):
    new_episode = Episode(title=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    # Set up storage directories
    storage_path = app_dir / "episodes" / new_episode.uuid
    storage_path.mkdir(parents=True, exist_ok=True)

    # Save uploaded files and create entries
    source_dir = storage_path / "source"
    source_dir.mkdir(exist_ok=True)

    try:
        for file in files:
            if not file.filename:
                return {"error": "No file name provided"}
            file_path = source_dir / file.filename
            with open(file_path, "wb") as f:
                content = await file.read()
                f.write(content)

        # Save all to database
        db.add(new_episode)
        job = ProcessingJob(episode_id=new_episode.uuid, type=JobType.preprocess, status=JobStatus.pending)
        db.add(job)
        db.commit()

        background_tasks.add_task(run_preprocessing, job.id, new_episode.uuid)

        return new_episode

    except Exception as e:
        return {"error": str(e)}


# Background preprocessing task
async def run_preprocessing(job_id: int, episode_uuid: str):
    print("Running preprocessing task")
    # db = get_db_session()

    # # Update job status
    # job = db.get(ProcessingJob, job_id)
    # job.status = "processing"
    # db.commit()

    # try:
    #     # Get episode
    #     episode = db.get(Episode, episode_uuid)
    #     source_dir = Path(episode.storage_path) / "source"
    #     output_dir = Path(episode.storage_path) / "preprocessed"
    #     output_dir.mkdir(exist_ok=True)

    #     # Prepare parameters for Waddle preprocessing
    #     reference_path = Path(reference_file.file_path) if reference_file else None

    #     # Run Waddle preprocessing function
    #     processed_files = preprocess_multi_files(reference=reference_path, source_dir=source_dir, output_dir=output_dir, generate_transcript=True)

    #     # Save processed file references to database
    #     for proc_file in processed_files:
    #         processed_file = ProcessedFile(
    #             episode_id=episode_uuid,
    #             filename=proc_file.name,
    #             file_path=str(proc_file),
    #             file_type="preprocessed",
    #             speaker_name=extract_speaker_name(proc_file.name),
    #         )
    #         db.add(processed_file)

    #     # Add transcription record
    #     srt_path = output_dir / "transcript.srt"
    #     if srt_path.exists():
    #         transcription = Transcription(episode_id=episode_uuid, file_path=str(srt_path), is_annotated=False)
    #         db.add(transcription)

    #     # Update episode status
    #     episode.preprocessed = True

    #     # Update job status
    #     job.status = "completed"

    # except Exception as e:
    #     # Handle errors
    #     job.status = "failed"
    #     job.error_message = str(e)

    # finally:
    #     db.commit()
    #     db.close()
