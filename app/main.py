from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.types import Scope

from app.db import db
from app.routers import invoices_api, models_api, pages, runs_api, ws_api


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.connect()
    app.state.background_tasks = set()
    yield
    await db.close()


class RevalidatingStaticFiles(StaticFiles):
    """Forces the browser to revalidate (via ETag/Last-Modified) on every load
    instead of relying on heuristic caching — this app's CSS/JS change frequently
    across commits, and without an explicit Cache-Control header some browsers
    silently keep serving a stale cached copy after a rebuild."""

    async def get_response(self, path: str, scope: Scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        return response


app = FastAPI(title="Invoice Scan Comparison Tool", lifespan=lifespan)
app.mount("/static", RevalidatingStaticFiles(directory="static"), name="static")

app.include_router(pages.router)
app.include_router(models_api.router)
app.include_router(invoices_api.router)
app.include_router(runs_api.router)
app.include_router(ws_api.router)
