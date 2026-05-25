from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.api.routes import router
from app.api.ui_routes import router as ui_router
from app.db.base import Base
from app.db.session import engine
from app.utils.log_config import setup_logging

setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


app = FastAPI(
    title="WhatsApp CRM Review Intelligence",
    description="Scrape Google Reviews for WhatsApp CRM companies and generate AI insights",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(router, prefix="/api/v1")
app.include_router(ui_router, prefix="/api/v1")

app.mount("/static", StaticFiles(directory="app/static"), name="static")

@app.get("/")
async def root():
    return FileResponse("app/static/index.html")
