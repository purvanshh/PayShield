"""Read-only meta endpoints serving committed measured artifacts.

The dashboard never re-derives its own numbers — it renders what the backend
actually measured and committed under ``models/``:

- ``/v1/meta/return-risk/benchmark`` -> ``models/return_risk_benchmark_results.json``
- ``/v1/meta/return-risk/cost``       -> ``models/cost_model_results.json``
  (regenerated on demand from ``docs/cost_model/calculator.py`` if missing)
- ``/v1/meta/experiments``            -> ``models/ab_test_result.json``

Authentication follows the standard API-key/Bearer path; these are read-only
introspection endpoints with no side effects besides cache generation.
"""

import json
import logging
import subprocess
import sys
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import verify_api_key

logger = logging.getLogger(__name__)

router = APIRouter(tags=["meta"])

ROOT = Path(__file__).resolve().parents[2]
_BENCHMARK = ROOT / "models" / "return_risk_benchmark_results.json"
_COST = ROOT / "models" / "cost_model_results.json"
_AB = ROOT / "models" / "ab_test_result.json"


def _load(path: Path):
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


@router.get("/v1/meta/return-risk/benchmark")
async def return_risk_benchmark(
    _=Depends(verify_api_key),  # noqa: B008 - FastAPI dependency-injection idiom
):
    """The committed calibrated benchmark (PR-AUC / ROC / gate metrics)."""
    data = _load(_BENCHMARK)
    if data is None:
        raise HTTPException(status_code=404, detail="benchmark results not found")
    return data


@router.get("/v1/meta/return-risk/cost")
async def return_risk_cost(
    _=Depends(verify_api_key),  # noqa: B008 - FastAPI dependency-injection idiom
):
    """The cost model (scenarios + sensitivity + operating point).

    Serves the committed ``cost_model_results.json``; if absent, regenerates it
    from the authoritative calculator and caches it under ``models/``.
    """
    data = _load(_COST)
    if data is None:
        try:
            import asyncio

            await asyncio.to_thread(
                subprocess.check_call,
                [sys.executable, "docs/cost_model/calculator.py", "--json"],
                cwd=ROOT,
            )
            logger.info("regenerated %s", _COST.name)
        except Exception as exc:  # nosec B110 - cache regeneration is best-effort
            logger.warning("cost model regeneration failed: %s", exc)
        data = _load(_COST)
    if data is None:
        raise HTTPException(status_code=503, detail="cost model results unavailable")
    return data


@router.get("/v1/meta/experiments")
async def experiments(
    _=Depends(verify_api_key),  # noqa: B008 - FastAPI dependency-injection idiom
):
    """The committed champion/challenger A/B verdict (real simulation output)."""
    data = _load(_AB)
    if data is None:
        raise HTTPException(status_code=404, detail="a/b test result not found")
    return data
