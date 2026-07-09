from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.db import db
from app.routers import models_api, pages, runs_api, ws_api


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.connect()
    app.state.background_tasks = set()
    yield
    await db.close()


app = FastAPI(title="Invoice Scan Comparison Tool", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(pages.router)
app.include_router(models_api.router)
app.include_router(runs_api.router)
app.include_router(ws_api.router)
