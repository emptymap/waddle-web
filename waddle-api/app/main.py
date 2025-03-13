from contextlib import asynccontextmanager
from typing import Annotated, List

from fastapi import Depends, FastAPI, HTTPException, Query, UploadFile, status
from sqlmodel import Session, select

from app.db import create_db_and_tables, get_session
from app.models import (
    Episode,
    EpisodeCreate,
    EpisodeUpdate,
)

SessionDep = Annotated[Session, Depends(get_session)]


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    yield


app = FastAPI(lifespan=lifespan)


# Episode CRUD endpoints
@app.post(
    "/episodes/", response_model=Episode, status_code=status.HTTP_201_CREATED
)
def create_episode(
    episode: EpisodeCreate, session: SessionDep, files: List[UploadFile]
):
    print(files)
    db_episode = Episode.model_validate(episode)
    session.add(db_episode)
    session.commit()
    session.refresh(db_episode)
    return db_episode


@app.get("/episodes/", response_model=List[Episode])
def read_episodes(
    session: SessionDep,
    offset: int = 0,
    limit: Annotated[int, Query(le=100)] = 100,
):
    episodes = session.exec(select(Episode).offset(offset).limit(limit)).all()
    return episodes


@app.get("/episodes/{episode_uuid}", response_model=Episode)
def read_episode(episode_uuid: str, session: SessionDep):
    episode = session.get(Episode, episode_uuid)
    if not episode:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Episode not found",
        )
    return episode


@app.patch("/episodes/{episode_uuid}", response_model=Episode)
def update_episode(
    episode_uuid: str, episode: EpisodeUpdate, session: SessionDep
):
    db_episode = session.get(Episode, episode_uuid)
    if not db_episode:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Episode not found",
        )
    episode_data = episode.model_dump(exclude_unset=True)
    db_episode.sqlmodel_update(episode_data)
    session.add(db_episode)
    session.commit()
    session.refresh(db_episode)
    return db_episode


@app.delete("/episodes/{episode_uuid}", status_code=status.HTTP_204_NO_CONTENT)
def delete_episode(episode_uuid: str, session: SessionDep):
    episode = session.get(Episode, episode_uuid)
    if not episode:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Episode not found",
        )
    session.delete(episode)
    session.commit()
    return None
