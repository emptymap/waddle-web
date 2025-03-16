from datetime import datetime
from pathlib import Path
from typing import Annotated, List

from fastapi import APIRouter, BackgroundTasks, Depends, Query, UploadFile
from platformdirs import user_data_dir
from sqlmodel import Session, select
from waddle.processor import preprocess_multi_files

from app.db import get_session
from app.defaults import APP_AUTHOR, APP_NAME
from app.models import Episode, JobStatus, JobType, ProcessingJob, UpdateEpisodeRequest

SessionDep = Annotated[Session, Depends(get_session)]
app_dir = Path(user_data_dir(APP_NAME, APP_AUTHOR))

# Create v1 router
v1_router = APIRouter(tags=["v1"])


# Episode CRUD endpoints
@v1_router.get("/episodes/", response_model=List[Episode])
def read_episodes(
    session: SessionDep,
    offset: Annotated[int, Query(ge=0, description="Offset the number of episodes returned")] = 0,
    limit: Annotated[int, Query(le=100, description="Limit the number of episodes returned")] = 100,
):
    """Read all episodes"""
    episodes = session.exec(select(Episode).offset(offset).limit(limit)).all()
    return episodes


@v1_router.post("/episodes/")
async def create_episode(files: list[UploadFile], db: SessionDep, background_tasks: BackgroundTasks):
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

        background_tasks.add_task(run_preprocessing, job.id, new_episode.uuid, db)

        return new_episode

    except Exception as e:
        return {"error": str(e)}


@v1_router.patch("/episodes/{episode_id}", response_model=Episode)
def update_episode(episode_id: str, update_data: UpdateEpisodeRequest, session: SessionDep):
    """Update an existing episode"""
    episode = session.get(Episode, episode_id)
    if not episode:
        return {"error": "Episode not found"}

    update_dict = update_data.model_dump(exclude_unset=True)
    for key, value in update_dict.items():
        setattr(episode, key, value)

    session.add(episode)
    session.commit()
    session.refresh(episode)

    return episode


# Background preprocessing task
def run_preprocessing(job_id: int, episode_uuid: str, db: Session):
    job = db.get(ProcessingJob, job_id)
    if not job:
        return

    episode = db.get(Episode, episode_uuid)
    if not episode:
        return

    job.status = JobStatus.processing
    db.commit()

    try:
        episode_dir = app_dir / "episodes" / episode_uuid
        preprocess_multi_files(reference=None, source_dir=episode_dir / "source", output_dir=episode_dir / "preprocessed")
        episode.preprocessed = True
        job.status = JobStatus.completed

    except Exception as e:
        job.status = JobStatus.failed
        job.error_message = str(e)

    finally:
        db.commit()
        db.close()
