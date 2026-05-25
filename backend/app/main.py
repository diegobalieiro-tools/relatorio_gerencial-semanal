from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes_dictionaries import router as dictionaries_router
from app.api.routes_historico import router as historico_router
from app.api.routes_obras import router as obras_router
from app.api.routes_pipeline import router as pipeline_router
from app.api.routes_relatorios import router as relatorios_router
from app.core.config import get_settings


settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    debug=settings.app_debug,
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(obras_router)
app.include_router(relatorios_router)
app.include_router(pipeline_router)
app.include_router(dictionaries_router)
app.include_router(historico_router)


@app.get("/api/health", tags=["Health"])
def health_check() -> dict[str, str]:
    return {
        "status": "ok",
        "app": settings.app_name,
        "env": settings.app_env,
    }
