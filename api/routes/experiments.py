import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.dependencies import get_redis
from api.rbac import require_permission

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


_framework: Any = None


def _get_framework():
    """Return the process-level A/B framework (in-memory by design; swap for a
    persistent backend when multi-instance deployment is required)."""
    global _framework
    if _framework is None:
        from ml.ab_testing import ABTestFramework
        _framework = ABTestFramework()
    return _framework


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
        raise HTTPException(status_code=400, detail=str(e)) from e


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
        raise HTTPException(status_code=400, detail=str(e)) from e


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
        raise HTTPException(status_code=400, detail=str(e)) from e


# --------------------------------------------------------------------------- #
# Track 2: champion/challenger experiments for return-risk weights            #
# --------------------------------------------------------------------------- #


class ReturnRiskExperimentCreateRequest(BaseModel):
    champion_weights: dict[str, float]
    challenger_weights: dict[str, float]
    traffic_split: float = Field(default=0.10, gt=0, le=0.5)


class ReturnRiskExperimentResponse(BaseModel):
    experiment_id: str
    status: str
    traffic_split: float
    champion_weights: dict[str, float]
    challenger_weights: dict[str, float]
    created_at: str


class ReturnRiskEvaluationRequest(BaseModel):
    champion: list[float]
    challenger: list[float]


class ReturnRiskEvaluationResponse(BaseModel):
    experiment_id: str
    champion_precision: float
    challenger_precision: float
    improvement: float
    significant: bool
    recommendation: str


@router.post("/return-risk", response_model=ReturnRiskExperimentResponse)
async def create_return_risk_experiment(
    req: ReturnRiskExperimentCreateRequest,
    redis=Depends(get_redis),
    _=Depends(require_permission("model", "promote")),
):
    """Start a champion/challenger experiment on return-risk weights."""
    from ml.ab_testing import ReturnRiskABExperiment

    experiment = ReturnRiskABExperiment(redis)
    data = await experiment.create_experiment(
        champion_weights=req.champion_weights,
        challenger_weights=req.challenger_weights,
        traffic_split=req.traffic_split,
    )
    return ReturnRiskExperimentResponse(
        experiment_id=data["experiment_id"],
        status=data["status"],
        traffic_split=data["traffic_split"],
        champion_weights=data["champion"]["weights"],
        challenger_weights=data["challenger"]["weights"],
        created_at=data["created_at"],
    )


@router.post(
    "/return-risk/{experiment_id}/evaluate", response_model=ReturnRiskEvaluationResponse
)
async def evaluate_return_risk_experiment(
    experiment_id: str,
    req: ReturnRiskEvaluationRequest,
    redis=Depends(get_redis),
    _=Depends(require_permission("model", "promote")),
):
    """Evaluate a return-risk weight experiment from observed outcomes."""
    from ml.ab_testing import ReturnRiskABExperiment

    experiment = ReturnRiskABExperiment(redis, experiment_id=experiment_id)
    evaluation = await experiment.evaluate_experiment(
        outcomes={"champion": req.champion, "challenger": req.challenger}
    )
    return ReturnRiskEvaluationResponse(**evaluation)
