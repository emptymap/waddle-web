from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from platformdirs import user_data_dir

from app.db import create_db_and_tables
from app.defaults import APP_AUTHOR, APP_NAME
from app.v1.router import v1_router

app_dir = Path(user_data_dir(APP_NAME, APP_AUTHOR))


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    yield


app = FastAPI(lifespan=lifespan)
app.include_router(v1_router, prefix="/v1")
