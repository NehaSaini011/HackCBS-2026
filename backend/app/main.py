import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import yb
from app.settings import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Runs once when the server starts, and the part after `yield` once when it stops.
    yb.pool.open(wait=True, timeout=15)   # fail fast if YugabyteDB is unreachable
    yield
    yb.pool.close()


app = FastAPI(title="Fix Network Group API", lifespan=lifespan)

# CORS: the browser only lets the web app call us if we name its address here.
origins = [o.strip() for o in settings.allowed_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"ok": True}


if os.environ.get("USE_STUBS") == "true":
    # Hour 1 only: fixed example answers so Persons 1 and 3 can start connecting.
    from app import stubs
    app.include_router(stubs.router)
else:
    from app import routes_agent, routes_auth, routes_ingest, routes_web
    for module in (routes_auth, routes_ingest, routes_web, routes_agent):
        app.include_router(module.router)