from contextlib import asynccontextmanager

from fastapi import FastAPI

from core.exceptions import AppException
from core.health import router as health_router
from core.middlewares.exception_handler import app_exception_handler
from core.middlewares.request_id import RequestIDMiddleware
from core.s3 import s3_client_context
from core.sqs import sqs_client_context
from routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with s3_client_context() as s3_client, sqs_client_context() as sqs_client:
        app.state.s3_client = s3_client
        app.state.sqs_client = sqs_client
        yield


app = FastAPI(lifespan=lifespan)

app.add_middleware(RequestIDMiddleware)
app.include_router(router)
app.include_router(health_router)
app.add_exception_handler(AppException, app_exception_handler)
