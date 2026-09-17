import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.api import auth, kpis, suppliers, inventory, forecasting, anomalies, risk, simulator, recommendations, catalog, admin

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("chainsight")

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Supply Chain Intelligence & Decision Support Platform API",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(SQLAlchemyError)
async def db_exception_handler(request: Request, exc: SQLAlchemyError):
    logger.exception("Database error on %s", request.url)
    return JSONResponse(status_code=500, content={"detail": "A database error occurred. Please try again."})


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s", request.url)
    return JSONResponse(status_code=500, content={"detail": "An unexpected error occurred."})


@app.get("/health")
def health_check():
    return {"status": "ok", "service": settings.PROJECT_NAME}


app.include_router(auth.router)
app.include_router(kpis.router)
app.include_router(suppliers.router)
app.include_router(inventory.router)
app.include_router(forecasting.router)
app.include_router(anomalies.router)
app.include_router(risk.router)
app.include_router(simulator.router)
app.include_router(recommendations.router)
app.include_router(catalog.router)
app.include_router(admin.router)
