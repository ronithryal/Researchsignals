from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.api.routes.phase4 import router as phase4_router
from app.config import settings
from app.logging_config import setup_logging
from app.scheduler import start_scheduler, stop_scheduler

app = FastAPI(title="DeFi Signal Terminal")


@app.on_event("startup")
async def on_startup() -> None:
    setup_logging(json_logs=settings.json_logs)
    start_scheduler()


@app.on_event("shutdown")
async def on_shutdown() -> None:
    stop_scheduler()

# serve the frontend prototype
app.mount("/static", StaticFiles(directory="frontend"), name="static")


@app.get("/")
async def serve_frontend():
    return FileResponse("frontend/index.html")


@app.get("/health")
async def health():
    return {"status": "ok"}


# routers added in later phases
app.include_router(phase4_router)
