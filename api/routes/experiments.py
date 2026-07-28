import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/experiments", tags=["experiments"])


class ExperimentCreateRequest(BaseModel):
    name: str
    challenger_version: str
    traffic_split: float = 0.0
    duration_days: int = 14
    experiment_type: str = "MODEL_CHALLENGER"
    champion_version: str = ""


class ExperimentResponse(BaseModel):
    experiment_id: str
    name: str
    status: str
    traffic_split: float
    created_at: str


class ExperimentMetricsResponse(BaseModel):
    experiment_id: str
    champion_metrics: dict[str, float]
    challenger_metrics: dict[str, float]
    p_value: float
    statistically_significant: bool
    winner: str
    recommendation: str


def _get_framework():
    from ml.ab_testing import ABTestFramework
    return ABTestFramework()


@router.post("", response_model=ExperimentResponse)
async def create_experiment(req: ExperimentCreateRequest):
    try:
        framework = _get_framework()
        exp = framework.register_experiment(
            name=req.name,
            challenger_version=req.challenger_version,
            traffic_split=req.traffic_split,
            duration_days=req.duration_days,
            experiment_type=req.experiment_type,
            champion_version=req.champion_version,
            created_by="admin",
        )
        return ExperimentResponse(
            experiment_id=exp.experiment_id,
            name=exp.name,
            status=exp.status,
            traffic_split=exp.traffic_split,
            created_at=exp.created_at,
        )
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("")
async def list_experiments():
    framework = _get_framework()
    exps = framework.list_experiments()
    return [
        ExperimentResponse(
            experiment_id=e.experiment_id,
            name=e.name,
            status=e.status,
            traffic_split=e.traffic_split,
            created_at=e.created_at,
        )
        for e in exps
    ]


@router.get("/{experiment_id}/results", response_model=ExperimentMetricsResponse)
async def get_experiment_results(experiment_id: str):
    framework = _get_framework()
    exp = framework.get_experiment(experiment_id)
    if not exp:
        raise HTTPException(status_code=404, detail="Experiment not found")

    result = framework.evaluate_experiment(experiment_id)
    return ExperimentMetricsResponse(
        experiment_id=result.experiment_id,
        champion_metrics=result.champion_metrics,
        challenger_metrics=result.challenger_metrics,
        p_value=result.p_value,
        statistically_significant=result.statistically_significant,
        winner=result.winner,
        recommendation=result.recommendation,
    )


@router.post("/{experiment_id}/promote")
async def promote_experiment(experiment_id: str):
    framework = _get_framework()
    exp = framework.get_experiment(experiment_id)
    if not exp:
        raise HTTPException(status_code=404, detail="Experiment not found")
    try:
        framework.promote(experiment_id)
        return {"status": "promoted", "experiment_id": experiment_id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{experiment_id}/rollback")
async def rollback_experiment(experiment_id: str):
    framework = _get_framework()
    exp = framework.get_experiment(experiment_id)
    if not exp:
        raise HTTPException(status_code=404, detail="Experiment not found")
    try:
        framework.rollback(experiment_id)
        return {"status": "rolled_back", "experiment_id": experiment_id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
