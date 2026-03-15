import logging
import os

from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI
from starlette.middleware.cors import CORSMiddleware

from db import client
from routes.activity import router as activity_router
from routes.auth import router as auth_router
from routes.communications import router as communications_router
from routes.community import router as community_router
from routes.events import router as events_router
from routes.finance import router as finance_router
from routes.legacy import router as legacy_router
from routes.polls import router as polls_router
from routes.revenuecat import router as revenuecat_router
from routes.subscriptions import router as subscriptions_router
from routes.timeline import router as timeline_router

load_dotenv()

app = FastAPI(title="Kindred API")

# Health check
api_root = APIRouter(prefix="/api")


@api_root.get("/")
async def root():
    return {"message": "Kindred API is ready."}


# Include all domain routers
app.include_router(api_root)
app.include_router(activity_router)
app.include_router(auth_router)
app.include_router(community_router)
app.include_router(communications_router)
app.include_router(events_router)
app.include_router(finance_router)
app.include_router(legacy_router)
app.include_router(polls_router)
app.include_router(revenuecat_router)
app.include_router(subscriptions_router)
app.include_router(timeline_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
