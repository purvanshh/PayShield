from fastapi import APIRouter, Depends

from api.schemas import InvestigationReport
from api.dependencies import verify_api_key

router = APIRouter(dependencies=[Depends(verify_api_key)])


@router.get("/investigation/{txn_id}", response_model=InvestigationReport)
async def get_investigation(txn_id: str):
    pass
