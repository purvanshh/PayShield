from fastapi import APIRouter, Depends

from api.schemas import FeedbackRequest, FeedbackResponse
from api.dependencies import verify_api_key

router = APIRouter(dependencies=[Depends(verify_api_key)])


@router.post("/feedback", response_model=FeedbackResponse)
async def submit_feedback(feedback: FeedbackRequest):
    pass
