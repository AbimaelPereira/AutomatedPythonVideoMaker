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
from videos.router import router as videos_router
from subtitle_preview.router import router as subtitle_preview_router
from thumbnail_preview.router import router as thumbnail_preview_router
from youtube.router import router as youtube_router
import channels.models  # noqa: F401 — garante que a tabela é criada
import videos.models  # noqa: F401 — garante que a tabela é criada


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    yield


TAGS_METADATA = [
    {"name": "youtube",
     "description":
        "Upload, playlists e coleta de dados do YouTube, por canal.\n\n"
        "O `{slug}` é o nome do arquivo em `videomaker/channels_config/` "
        "(ex. `psychology_of_the_gospel`).\n\n"
        "Operações longas (upload de MP4, sync do canal) entram na fila de "
        "jobs e devolvem `job_id` — acompanhe em `GET /jobs/{id}`. O sync "
        "aceita `?wait=true` para rodar na própria request.\n\n"
        "Detalhes e pegadinhas: `videomaker/docs/YOUTUBE.md`."},
]

app = FastAPI(title="Canais Dark API", lifespan=lifespan,
              openapi_tags=TAGS_METADATA)

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
app.include_router(videos_router, prefix="/videos", tags=["videos"])
app.include_router(subtitle_preview_router, prefix="/subtitle-preview", tags=["subtitle-preview"])
app.include_router(thumbnail_preview_router, prefix="/thumbnail-preview", tags=["thumbnail-preview"])
app.include_router(youtube_router, prefix="/youtube", tags=["youtube"])


@app.get("/health")
def health():
    return {"status": "ok"}
