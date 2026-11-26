from fastapi import FastAPI

from assets.router import router as assets_router

app = FastAPI(title="Canais Dark API")

app.include_router(assets_router, prefix="/remote-assets", tags=["assets"])


@app.get("/health")
def health():
    return {"status": "ok"}
