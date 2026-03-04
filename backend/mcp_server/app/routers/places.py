from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.models.schemas import (
    AreaProfile,
    CompareAreasRequest,
    CompareAreasResponse,
    DemographicsCompareRequest,
    DemographicsCompareResponse,
    DemographicsProfile,
    DemographicsRequest,
    IndustryResearchRequest,
    IndustryResearchResponse,
    PlaceSummary,
    SearchPlacesRequest,
)
from app.services.places import PlaceService
from app.utils.logging import get_logger

router = APIRouter(prefix="/places", tags=["places"])
service = PlaceService()
logger = get_logger(__name__)


def _summary(value):
    if isinstance(value, list):
        return {"type": "list", "len": len(value)}
    if isinstance(value, dict):
        keys = list(value.keys())
        return {"type": "dict", "keys": keys[:10], "truncated": len(keys) > 10}
    return {"type": type(value).__name__, "value": str(value)[:200]}


@router.post("/geocode")
async def geocode(payload: dict[str, str]):
    query = payload.get("query")
    if not query:
        raise HTTPException(status_code=400, detail="query is required")
    logger.info("places.geocode.request", query=query)
    try:
        result = await service.geocode(query)
        logger.info("places.geocode.response", result=_summary(result))
        return result
    except ValueError as exc:  # pragma: no cover - FastAPI handles
        logger.exception("places.geocode.value_error", query=query)
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        logger.exception("places.geocode.runtime_error", query=query)
        raise HTTPException(status_code=429, detail=str(exc)) from exc


@router.post("/search", response_model=list[PlaceSummary])
async def search(payload: SearchPlacesRequest):
    logger.info("places.search.request", payload=_summary(payload.model_dump()))
    try:
        result = await service.search_places(payload)
        logger.info("places.search.response", result=_summary(result))
        return result
    except RuntimeError as exc:
        logger.exception("places.search.runtime_error", payload=_summary(payload.model_dump()))
        raise HTTPException(status_code=429, detail=str(exc)) from exc


@router.post("/profile", response_model=AreaProfile)
async def profile(payload: SearchPlacesRequest):
    try:
        focus_brand = payload.brand
        logger.info(
            "places.profile.request",
            focus_brand=focus_brand,
            payload=_summary(payload.model_dump()),
        )
        result = await service.summarize_area(payload, focus_brand=focus_brand)
        logger.info("places.profile.response", result=_summary(result.model_dump()))
        return result
    except ValueError as exc:
        logger.exception("places.profile.value_error", payload=_summary(payload.model_dump()))
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        logger.exception("places.profile.runtime_error", payload=_summary(payload.model_dump()))
        raise HTTPException(status_code=429, detail=str(exc)) from exc


@router.post("/compare", response_model=CompareAreasResponse)
async def compare(payload: CompareAreasRequest):
    try:
        logger.info("places.compare.request", payload=_summary(payload.model_dump()))
        result = await service.compare_areas(payload)
        logger.info("places.compare.response", result=_summary(result.model_dump()))
        return result
    except RuntimeError as exc:
        logger.exception("places.compare.runtime_error", payload=_summary(payload.model_dump()))
        raise HTTPException(status_code=429, detail=str(exc)) from exc


@router.post("/demographics", response_model=DemographicsProfile)
async def demographics(payload: DemographicsRequest):
    try:
        logger.info("places.demographics.request", payload=_summary(payload.model_dump()))
        result = await service.summarize_demographics(payload)
        logger.info("places.demographics.response", result=_summary(result.model_dump()))
        return result
    except ValueError as exc:
        logger.exception("places.demographics.value_error", payload=_summary(payload.model_dump()))
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        logger.exception("places.demographics.runtime_error", payload=_summary(payload.model_dump()))
        raise HTTPException(status_code=429, detail=str(exc)) from exc


@router.post("/demographics/compare", response_model=DemographicsCompareResponse)
async def compare_demographics(payload: DemographicsCompareRequest):
    try:
        logger.info("places.demographics_compare.request", payload=_summary(payload.model_dump()))
        result = await service.compare_demographics(payload)
        logger.info("places.demographics_compare.response", result=_summary(result.model_dump()))
        return result
    except ValueError as exc:
        logger.exception(
            "places.demographics_compare.value_error",
            payload=_summary(payload.model_dump()),
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        logger.exception(
            "places.demographics_compare.runtime_error",
            payload=_summary(payload.model_dump()),
        )
        raise HTTPException(status_code=429, detail=str(exc)) from exc


@router.post("/industries", response_model=IndustryResearchResponse)
async def industry_research(payload: IndustryResearchRequest):
    try:
        logger.info("places.industries.request", payload=_summary(payload.model_dump()))
        result = await service.summarize_industries(payload)
        logger.info("places.industries.response", result=_summary(result.model_dump()))
        return result
    except ValueError as exc:
        logger.exception("places.industries.value_error", payload=_summary(payload.model_dump()))
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        logger.exception("places.industries.runtime_error", payload=_summary(payload.model_dump()))
        raise HTTPException(status_code=429, detail=str(exc)) from exc
