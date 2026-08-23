import json
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import get_redis, verify_api_key
from api.rbac import require_permission
from api.schemas import ConfigUpdateRequest, ConfigUpdateResponse

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(verify_api_key)])


@router.post("/rules/reload")
async def reload_rules(
    redis=Depends(get_redis),
    _=Depends(require_permission("rule", "write")),
):
    try:
        import yaml
        from pathlib import Path
        rules_path = Path("configs/statistical_rules.yaml")
        if not rules_path.exists():
            raise HTTPException(status_code=404, detail="Rules config not found")
        with open(rules_path) as f:
            rules = yaml.safe_load(f)
        await redis.set("rules:statistical", json.dumps(rules))
        logger.info("Rules reloaded from configs/statistical_rules.yaml")
        return {"status": "reloaded", "file": str(rules_path), "rule_count": len(rules) if isinstance(rules, dict) else 0}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to reload rules: {e}")


@router.post("/models/promote")
async def promote_model(
    body: dict,
    _=Depends(require_permission("model", "promote")),
):
    version = body.get("version", "")
    stage = body.get("stage", "production")
    if not version:
        raise HTTPException(status_code=400, detail="version is required")
    try:
        from ml.registry import ModelRegistry
        registry = ModelRegistry()
        result = registry.promote(version, stage)
        logger.info(f"Model {version} promoted to {stage}")
        return {"status": "promoted", "version": version, "stage": stage, "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Model promotion failed: {e}")


@router.get("/models/current")
async def current_model(
    _=Depends(require_permission("model", "read")),
):
    """Return metadata of the currently promoted model version.

    Reads ``models/registry/latest/metadata.json`` (written at registration)
    and falls back to the auto-generated ``manifest.json`` / ``model_card.md``
    for older versions that predate the metadata convention.
    """
    from pathlib import Path
    try:
        latest = Path("models/registry/latest")
        if not latest.exists() or not latest.is_symlink():
            return {"status": "no_registered_version"}
        version_dir = latest.resolve()
        metadata_path = version_dir / "metadata.json"
        if metadata_path.exists():
            with open(metadata_path) as f:
                metadata = json.load(f)
        else:
            manifest_path = version_dir / "manifest.json"
            if manifest_path.exists():
                with open(manifest_path) as f:
                    metadata = json.load(f)
            else:
                return {"status": "no_metadata", "version": version_dir.name}
        metadata["_registry_path"] = str(version_dir)
        try:
            from ml.registry import ModelRegistry
            prod = ModelRegistry().get_production_model()
            metadata["_production_model"] = str(prod) if prod is not None else None
        except Exception:
            metadata["_production_model"] = None
        return metadata
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read current model: {e}")


@router.get("/agents/health")
async def agent_health(
    _=Depends(require_permission("agent", "manage")),
):
    agents_status = {}
    try:
        from agents.monitoring_agent import MonitoringAgent
        from agents.base import AgentConfig
        monitor = MonitoringAgent(AgentConfig(agent_id="admin_query", agent_type="MONITORING"))
        for agent_id in ["profile_agent", "transaction_agent", "collective_agent",
                         "mitigation_agent", "memory_agent", "human_review_agent", "monitoring_agent"]:
            agents_status[agent_id] = monitor._check_agent_health(agent_id)
    except Exception as e:
        logger.warning(f"Agent health check failed: {e}")
        agents_status = {"error": str(e)}
    return {
        "agents": agents_status,
        "count": len(agents_status),
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.post("/agents/{agent_id}/restart")
async def restart_agent(
    agent_id: str,
    _=Depends(require_permission("agent", "manage")),
):
    logger.info(f"Agent restart requested: {agent_id}")
    return {"status": "restart_initiated", "agent_id": agent_id}


@router.get("/config")
async def get_config(
    _=Depends(require_permission("rule", "write")),
):
    import yaml
    from pathlib import Path
    configs = {}
    for path in Path("configs").glob("*.yaml"):
        try:
            with open(path) as f:
                data = yaml.safe_load(f)
            configs[path.stem] = data
        except Exception:
            configs[path.stem] = {"error": "failed_to_load"}
    return {"configs": configs}


@router.post("/config/threshold", response_model=ConfigUpdateResponse)
async def update_threshold(
    body: ConfigUpdateRequest,
    redis=Depends(get_redis),
    _=Depends(require_permission("rule", "write")),
):
    key = f"config:threshold:{body.key}"
    old = await redis.get(key) or "not_set"
    await redis.set(key, json.dumps({"value": body.value, "updated_at": datetime.utcnow().isoformat()}))
    logger.info(f"Threshold updated: {body.key} = {body.value}")
    return ConfigUpdateResponse(
        status="updated",
        key=body.key,
        old_value=old,
        new_value=body.value,
    )


@router.get("/drift/psi")
async def drift_psi(
    redis=Depends(get_redis),
    _=Depends(require_permission("metrics", "read")),
):
    """PSI drift report: yesterday vs today feature distributions."""
    try:
        from observability.drift_report import compute_psi_report
        report = await compute_psi_report(redis)
        logger.info(f"Drift report generated: {report['status']} ({len(report['drifted_features'])} drifted)")
        return report
    except Exception as e:
        logger.error(f"Drift report failed: {e}")
        raise HTTPException(status_code=500, detail=f"Drift report failed: {e}")


@router.get("/drift/return-risk")
async def drift_return_risk(
    redis=Depends(get_redis),
    _=Depends(require_permission("metrics", "read")),
):
    """PSI drift report for the return-risk feature surface."""
    try:
        from observability.return_risk_drift import ReturnRiskDriftMonitor

        report = await ReturnRiskDriftMonitor(redis).check()
        logger.info(
            "return-risk drift: %s (%d features)",
            report["overall_status"],
            len(report["features"]),
        )
        return report
    except Exception as e:
        logger.error(f"return-risk drift failed: {e}")
        raise HTTPException(status_code=500, detail=f"Return-risk drift failed: {e}")
