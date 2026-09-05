from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.graph import router as graph_router
from app.api.health import router as health_router
from app.api.masks import router as masks_router
from app.api.projects import router as projects_router
from app.api.versions import router as versions_router
from app.core.config import settings

app = FastAPI(title="Clai API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def request_validation_error_response(
    _request: Request,
    error: RequestValidationError,
) -> JSONResponse:
    details = [
        {
            "type": detail["type"],
            "loc": detail["loc"],
            "msg": detail["msg"],
        }
        for detail in error.errors()
    ]
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={"detail": details},
    )


app.include_router(health_router)
app.include_router(projects_router)
app.include_router(graph_router)
app.include_router(masks_router)
app.include_router(versions_router)

if settings.artifact_storage_backend == "filesystem":
    settings.artifact_storage_path.mkdir(parents=True, exist_ok=True)
    app.mount(
        "/artifacts",
        StaticFiles(directory=settings.artifact_storage_path),
        name="artifacts",
    )
