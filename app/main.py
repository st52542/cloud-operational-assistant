import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.observability.logger import get_logger
from app.observability.metrics import metrics_store
from app.storage.database import init_db

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("event=startup message='Operational assistant starting'")
    init_db()
    metrics_store.reset()
    yield
    logger.info("event=shutdown message='Operational assistant stopping'")


app = FastAPI(
    title="Cloud-native Operational Assistant",
    description="Agent-assisted operational service for L1 support workflows",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    start_time = time.time()

    logger.info(
        "event=http_request_start",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
        },
    )

    response = await call_next(request)
    duration_ms = round((time.time() - start_time) * 1000, 2)

    metrics_store.record_http_request(request.method, request.url.path, response.status_code, duration_ms)

    logger.info(
        "event=http_request_end",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
        },
    )

    response.headers["X-Request-ID"] = request_id
    return response


app.include_router(router)
