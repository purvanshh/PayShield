from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import score, investigation, health, feedback

app = FastAPI(
    title="PayShield",
    description="Real-Time UPI Fraud Detection & Graph-Powered Investigation API",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, tags=["health"])
app.include_router(score.router, prefix="/v1", tags=["score"])
app.include_router(investigation.router, prefix="/v1", tags=["investigation"])
app.include_router(feedback.router, prefix="/v1", tags=["feedback"])
