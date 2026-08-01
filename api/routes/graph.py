import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from api.dependencies import verify_api_key

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(verify_api_key)])


class GraphInvestigationRequest(BaseModel):
    entity_id: str
    entity_type: str = "user"
    hops: int = 2


class GraphInvestigationResponse(BaseModel):
    entity_id: str
    entity_type: str
    network_score: float
    connected_entities: int
    risk_paths: list[dict[str, Any]]
    neighbors: list[dict[str, Any]]


class EntityCreateRequest(BaseModel):
    entity_id: str
    entity_type: str
    features: dict[str, Any] | None = None


class EntityLinkRequest(BaseModel):
    source_id: str
    target_id: str
    relation_type: str
    features: dict[str, Any] | None = None


def _get_graph_db(request):
    resources = getattr(request.app.state, "resources", {})
    shared = resources.get("graph_db")
    if shared is not None:
        return shared, "networkx"
    try:
        from store.neo4j_client import Neo4jGraphDB
        return Neo4jGraphDB(), "neo4j"
    except Exception:
        try:
            from store.graph_db import NetworkXGraphDB
            return NetworkXGraphDB(), "networkx"
        except Exception:
            raise HTTPException(status_code=503, detail="No graph database available")


@router.post("/investigate", response_model=GraphInvestigationResponse)
async def investigate_entity(req: GraphInvestigationRequest, request: Request):
    try:
        db, db_type = _get_graph_db(request)

        network = db.get_network_score(req.entity_id) if hasattr(db, "get_network_score") else {"network_score": 0.0, "connected_entities": 0, "risk_clusters": 0}
        risk_paths = []
        neighbors = []

        if hasattr(db, "get_neighbors"):
            n_ids = db.get_neighbors(req.entity_id)
            for nid in n_ids:
                attrs = db.get_node_attributes(nid) if hasattr(db, "get_node_attributes") else {}
                neighbors.append({"id": nid, "type": attrs.get("node_type", "unknown"), "attributes": attrs})

        return GraphInvestigationResponse(
            entity_id=req.entity_id,
            entity_type=req.entity_type,
            network_score=network.get("network_score", 0.0),
            connected_entities=network.get("connected_entities", 0),
            risk_paths=risk_paths,
            neighbors=neighbors,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Graph investigation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Graph investigation failed: {str(e)}")


@router.get("/network/{entity_id}")
async def get_entity_network(
    entity_id: str,
    request: Request,
    hops: int = Query(2, ge=1, le=5),
    entity_type: str = Query("user"),
):
    try:
        db, db_type = _get_graph_db(request)

        ego_graph = db.get_ego_graph(entity_id, hops=hops)
        nodes_list = []
        edges_list = []

        for node, attrs in ego_graph.nodes(data=True):
            clean_attrs = {k: v for k, v in attrs.items() if isinstance(v, (str, int, float, bool, type(None)))}
            nodes_list.append({"id": node, "type": attrs.get("node_type", "unknown"), "attributes": clean_attrs})

        for u, v, attrs in ego_graph.edges(data=True):
            edges_list.append({"source": u, "target": v, "type": attrs.get("edge_type", "unknown"), "attributes": {k: v for k, v in attrs.items() if k != "edge_type"}})

        network_score = db.get_network_score(entity_id) if hasattr(db, "get_network_score") else {"network_score": 0.0}

        return {
            "entity_id": entity_id,
            "entity_type": entity_type,
            "hops": hops,
            "network_score": network_score.get("network_score", 0.0),
            "nodes": nodes_list,
            "edges": edges_list,
            "total_nodes": len(nodes_list),
            "total_edges": len(edges_list),
            "backend": db_type,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Network query failed for {entity_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Network query failed: {str(e)}")


@router.post("/entity")
async def create_entity(req: EntityCreateRequest, request: Request):
    try:
        db, db_type = _get_graph_db(request)
        if hasattr(db, "create_entity"):
            db.create_entity(req.entity_id, req.entity_type, req.features)
        else:
            db.add_node(req.entity_id, req.entity_type, req.features)
        return {"status": "created", "entity_id": req.entity_id, "entity_type": req.entity_type}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/link")
async def link_entities(req: EntityLinkRequest, request: Request):
    try:
        db, _ = _get_graph_db(request)
        if hasattr(db, "link_entities"):
            db.link_entities(req.source_id, req.target_id, req.relation_type, req.features)
        else:
            db.add_edge(req.source_id, req.target_id, req.relation_type, **(req.features or {}))
        return {"status": "linked", "source": req.source_id, "target": req.target_id, "relation": req.relation_type}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/risk-paths")
async def find_risk_paths(
    request: Request,
    source_id: str = Query(...),
    target_id: str = Query(...),
    max_hops: int = Query(4, ge=1, le=6),
):
    try:
        db, _ = _get_graph_db(request)
        paths = db.find_risk_paths(source_id, target_id, max_hops) if hasattr(db, "find_risk_paths") else []
        return {"source_id": source_id, "target_id": target_id, "max_hops": max_hops, "paths": paths}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
async def graph_stats(request: Request):
    try:
        db, db_type = _get_graph_db(request)
        return {
            "backend": db_type,
            "node_count": db.node_count(),
            "edge_count": db.edge_count(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
