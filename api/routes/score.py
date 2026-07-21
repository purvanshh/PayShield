from fastapi import APIRouter, Depends

from api.schemas import TransactionEvent, FraudScoreResponse, BatchScoreRequest, BatchScoreResponse
from api.dependencies import verify_api_key

router = APIRouter(dependencies=[Depends(verify_api_key)])


@router.post("/score", response_model=FraudScoreResponse)
async def score_transaction(txn: TransactionEvent):
    pass


@router.post("/batch", response_model=BatchScoreResponse)
async def batch_score(batch: BatchScoreRequest):
    pass
