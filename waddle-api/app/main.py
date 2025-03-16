from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db import create_db_and_tables
from app.v1.router import v1_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    yield


app = FastAPI(
    title="Waddle API",
    description="API for managing episodes and processing jobs in Waddle UI.",
    version="0.1.0",
    lifespan=lifespan,
)
app.include_router(v1_router, prefix="/v1")