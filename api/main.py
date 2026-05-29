from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from config import settings
from database import create_db_and_tables
from auth.router import router as auth_router
from admin.router import router as admin_router
from assets.router import router as assets_router
from jobs.router import router as jobs_router
from reelscutter_api.router import router as reelscutter_router
from channels.router import router as channels_router
import channels.models  # noqa: F401 — garante que a tabela é criada


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    yield


app = FastAPI(title="Canais Dark API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(admin_router, tags=["admin"])
app.include_router(assets_router, prefix="/remote-assets", tags=["assets"])
app.include_router(jobs_router, prefix="/jobs", tags=["jobs"])
app.include_router(reelscutter_router, prefix="/reelscutter", tags=["reelscutter"])
app.include_router(channels_router, prefix="/channels", tags=["channels"])


@app.get("/health")
def health():
    return {"status": "ok"}
