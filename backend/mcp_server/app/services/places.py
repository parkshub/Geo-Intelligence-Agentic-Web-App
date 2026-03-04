from __future__ import annotations

import difflib
import hashlib
import json
import re
from typing import Any

from app.clients.census import CensusClient
from app.clients.geoapify import GeoapifyClient
from app.clients.overpass import OverpassClient, build_place_query
from app.config import get_settings
from app.models.schemas import (
    AreaProfile,
    CompareAreasRequest,
    CompareAreasResponse,
    DemographicsBenchmark,
    DemographicsCompareRequest,
    DemographicsCompareResponse,
    DemographicsProfile,
    DemographicsRequest,
    IndustryBucket,
    IndustryResearchRequest,
    IndustryResearchResponse,
    PlaceSummary,
    SearchPlacesRequest,
)
from app.services.cache import cache_service
from app.services.metrics import demand_proxy_score, saturation_score
from app.utils.logging import get_logger

logger = get_logger(__name__)

DEFAULT_CATEGORIES = [
    "catering",
    "commercial",
    "service",
]


INDUSTRY_CATEGORY_SEEDS = [
    "catering",
    "commercial",
    "service",
    "healthcare",
    "education",
    "entertainment",
    "leisure",
    "sport",
    "tourism",
    "office",
    "accommodation",
    "childcare",
    "production",
    "pet",
]

INDUSTRY_LABELS = {
    "accommodation": "Accommodation",
    "catering": "Food & Beverage",
    "childcare": "Childcare",
    "commercial": "Retail & Commerce",
    "education": "Education",
    "entertainment": "Entertainment",
    "healthcare": "Healthcare",
    "leisure": "Leisure & Recreation",
    "office": "Office & Business",
    "pet": "Pet Services",
    "production": "Production",
    "service": "Local Services",
    "sport": "Sports & Fitness",
    "tourism": "Tourism",
}

NON_INDUSTRY_TAGS = {
    "access",
    "access_limited",
    "no_access",
    "named",
    "wheelchair",
    "fee",
    "no_fee",
    "internet_access",
    "dogs",
    "no_dogs",
    "vegetarian",
    "vegan",
    "halal",
    "kosher",
    "organic",
    "gluten_free",
    "sugar_free",
    "egg_free",
    "soy_free",
}


def _hash_key(prefix: str, payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True).encode("utf-8")
    return f"{prefix}:{hashlib.sha256(raw).hexdigest()}"


def _normalize_categories(categories: list[str] | None) -> list[str]:
    normalized, _ = _normalize_categories_with_meta(categories)
    return normalized


def _normalize_categories_with_meta(categories: list[str] | None) -> tuple[list[str], bool]:
    normalized = [(category or "").strip().lower() for category in (categories or [])]
    deduped = [value for value in dict.fromkeys(normalized) if value]
    return (deduped or DEFAULT_CATEGORIES.copy(), False)


def _normalize_text(value: str | None) -> str:
    if not value:
        return ""
    normalized = re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()
    return re.sub(r"\s+", " ", normalized)


def _matches_focus_brand(place: PlaceSummary, focus_brand: str) -> bool:
    focus = _normalize_text(focus_brand)
    brand = _normalize_text(place.brand)
    name = _normalize_text(place.name)

    if not focus:
        return False

    # Keep generic behavior unchanged for non-Starbucks brands.
    if focus != "starbucks":
        return brand == focus

    if brand in STARBUCKS_ALIASES:
        return True
    if any(alias in name for alias in STARBUCKS_ALIASES):
        return True
    if "starbucks" in name:
        return True

    # Starbucks-specific fuzzy fallback for minor naming variations/typos.
    for alias in STARBUCKS_ALIASES:
        if difflib.SequenceMatcher(a=name, b=alias).ratio() >= 0.9:
            return True
        name_tokens = name.split()
        alias_tokens = alias.split()
        window = len(alias_tokens)
        if window and len(name_tokens) >= window:
            for idx in range(len(name_tokens) - window + 1):
                chunk = " ".join(name_tokens[idx : idx + window])
                if difflib.SequenceMatcher(a=chunk, b=alias).ratio() >= 0.9:
                    return True
    return False


def _unique_places_by_name(places: list[PlaceSummary]) -> list[PlaceSummary]:
    """De-duplicate places by normalized display name."""
    seen: set[str] = set()
    unique: list[PlaceSummary] = []
    for place in places:
        key = _normalize_text(place.name) or f"place:{place.place_id}"
        if key in seen:
            continue
        seen.add(key)
        unique.append(place)
    return unique


def _to_int(row: dict[str, Any], key: str) -> int | None:
    value = row.get(key)
    if value in (None, "", "-666666666"):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_float(row: dict[str, Any], key: str) -> float | None:
    value = row.get(key)
    if value in (None, "", "-666666666"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _pct(part: int | None, whole: int | None) -> float | None:
    if part is None or whole in (None, 0):
        return None
    return round((part / whole) * 100, 2)


def _benchmark_from_row(row: dict[str, Any]) -> DemographicsBenchmark:
    population_total = _to_int(row, "B01003_001E")
    median_household_income = _to_int(row, "B19013_001E")
    median_age = _to_float(row, "B01002_001E")
    households_total = _to_int(row, "B11001_001E")

    edu_total = _to_int(row, "B15003_001E")
    bachelor_plus = sum(
        (value or 0)
        for value in (
            _to_int(row, "B15003_022E"),
            _to_int(row, "B15003_023E"),
            _to_int(row, "B15003_024E"),
            _to_int(row, "B15003_025E"),
        )
    )

    poverty_universe = _to_int(row, "B17001_001E")
    poverty_below = _to_int(row, "B17001_002E")

    race_total = _to_int(row, "B02001_001E")
    race_white = _to_int(row, "B02001_002E")
    race_black = _to_int(row, "B02001_003E")
    race_asian = _to_int(row, "B02001_005E")

    hisp_total = _to_int(row, "B03003_001E")
    hisp_count = _to_int(row, "B03003_003E")

    return DemographicsBenchmark(
        population_total=population_total,
        median_household_income=median_household_income,
        median_age=median_age,
        households_total=households_total,
        education_bachelor_plus_pct=_pct(bachelor_plus, edu_total),
        poverty_rate_pct=_pct(poverty_below, poverty_universe),
        race_white_pct=_pct(race_white, race_total),
        race_black_pct=_pct(race_black, race_total),
        race_asian_pct=_pct(race_asian, race_total),
        hispanic_pct=_pct(hisp_count, hisp_total),
    )


def _industry_from_categories(categories: list[str]) -> str:
    for category in categories:
        top_level = category.split(".", 1)[0].strip().lower()
        if not top_level or top_level in NON_INDUSTRY_TAGS:
            continue
        return top_level
    return "other"


class PlaceService:
    def __init__(self) -> None:
        settings = get_settings()
        self._geo_client = GeoapifyClient(settings.geoapify)
        self._census_client = CensusClient(settings.census)
        self._overpass_client = OverpassClient(settings.overpass)
        self._geo_settings = settings.geoapify
        self._overpass_settings = settings.overpass
        self._credit_estimate = 0

    async def geocode(self, query: str) -> dict[str, Any]:
        cache_key = _hash_key("geocode", {"query": query})

        async def _factory() -> dict[str, Any]:
            logger.info("geocode.fetch", query=query)
            self._reserve_credits(1)
            return await self._geo_client.geocode(query)

        return await cache_service.get_or_set(cache_key, ttl_seconds=60 * 60, factory=_factory)

    async def search_places(self, payload: SearchPlacesRequest) -> list[PlaceSummary]:
        lat, lon = payload.lat, payload.lon
        if (lat is None or lon is None) and payload.location:
            resolved = await self.geocode(payload.location)
            lat, lon = resolved["lat"], resolved["lon"]
            payload = payload.model_copy(update={"lat": lat, "lon": lon})
        if lat is None or lon is None:
            raise ValueError("Either location or lat/lon must be provided")

        categories, _ = _normalize_categories_with_meta(payload.categories)
        params = {
            "lat": lat,
            "lon": lon,
            "radius_m": min(payload.radius_m, self._overpass_settings.radius_limit_m),
            "categories": categories,
            "brand": payload.brand,
            "name": payload.name,
        }
        cache_key = _hash_key("search", params)

        async def _factory() -> list[PlaceSummary]:
            logger.info("places.search", params=params)
            estimated_cost = 1 + int((self._geo_settings.default_limit or 20) / 20)
            self._reserve_credits(estimated_cost)
            features = await self._geo_client.search_places(
                lat=lat,
                lon=lon,
                radius_m=params["radius_m"],
                categories=categories,
                name=payload.name,
            )
            summaries = [
                PlaceSummary(
                    place_id=str(feature["properties"]["place_id"]),
                    name=(
                        feature["properties"].get("name")
                        or feature["properties"].get("formatted")
                        or "Unnamed place"
                    ),
                    categories=feature["properties"].get("categories") or [],
                    brand=feature["properties"].get("brand"),
                    distance_m=feature["properties"].get("distance", 0.0),
                    lat=(
                        (feature.get("geometry") or {}).get("coordinates", [None, None])[1]
                        if isinstance((feature.get("geometry") or {}).get("coordinates"), list)
                        else None
                    ),
                    lon=(
                        (feature.get("geometry") or {}).get("coordinates", [None, None])[0]
                        if isinstance((feature.get("geometry") or {}).get("coordinates"), list)
                        else None
                    ),
                    rank_popularity=feature["properties"].get("rank", {}).get("popularity"),
                    opening_hours=feature["properties"].get("opening_hours"),
                    datasource="geoapify",
                )
                for feature in features
            ]
            if payload.brand:
                # augment with Overpass brand-specific data for reliability
                query = build_place_query(
                    lat=lat,
                    lon=lon,
                    radius_m=params["radius_m"],
                    brand=payload.brand,
                    timeout=self._overpass_settings.timeout_seconds,
                )
                try:
                    overpass = await self._overpass_client.run_query(query)
                    for element in overpass.get("elements", []):
                        name = element.get("tags", {}).get("name")
                        place_id = f"overpass:{element.get('id')}"
                        summaries.append(
                            PlaceSummary(
                                place_id=place_id,
                                name=name or payload.brand or "Brand location",
                                categories=[element.get("tags", {}).get("amenity", "poi")],
                                brand=element.get("tags", {}).get("brand"),
                                distance_m=element.get("tags", {}).get("distance", 0.0),
                                lat=element.get("lat"),
                                lon=element.get("lon"),
                                opening_hours=element.get("tags", {}).get("opening_hours"),
                                rank_popularity=None,
                                datasource="overpass",
                            )
                        )
                except Exception as exc:
                    # Overpass is a best-effort augmentation; do not fail the whole request.
                    logger.warning(
                        "places.search.overpass_fallback",
                        error=str(exc),
                        brand=payload.brand,
                        radius_m=params["radius_m"],
                    )
            return summaries

        return await cache_service.get_or_set(cache_key, ttl_seconds=60 * 60 * 6, factory=_factory)

    async def summarize_area(
        self,
        payload: SearchPlacesRequest,
        *,
        focus_brand: str | None = None,
    ) -> AreaProfile:
        target_payload = payload
        if (payload.lat is None or payload.lon is None) and payload.location:
            coords = await self.geocode(payload.location)
            target_payload = payload.model_copy(update={"lat": coords["lat"], "lon": coords["lon"]})
        places = await self.search_places(target_payload)
        centroid = (target_payload.lat or 0.0, target_payload.lon or 0.0)
        normalized_focus_brand = (focus_brand or "").strip()
        brand_count = (
            sum(1 for place in places if _matches_focus_brand(place, normalized_focus_brand))
            if normalized_focus_brand
            else 0
        )
        competitor_count = len(places)
        closest_unique_competitors = _unique_places_by_name(
            sorted(
                places,
                key=lambda p: (
                    p.distance_m if isinstance(p.distance_m, (int, float)) else float("inf"),
                    -(p.rank_popularity or 0),
                ),
            )
        )
        # Keep enough points for map rendering while preserving closest-first ordering.
        top_competitors = closest_unique_competitors[:20]
        saturation = saturation_score(
            brand_count=brand_count,
            competitor_count=competitor_count - brand_count,
            radius_m=payload.radius_m,
        )
        demand = demand_proxy_score(competitors=places, brand_count=brand_count)
        notes = []
        if demand < 40:
            notes.append("Low demand proxy score—consider awareness campaigns.")
        elif demand > 80:
            notes.append("High demand proxy score—optimize for conversion with premium placements.")
        label = target_payload.location or f"{target_payload.lat},{target_payload.lon}"
        return AreaProfile(
            query=label,
            centroid=centroid,
            brand_count=brand_count,
            competitor_count=competitor_count,
            saturation_score=saturation,
            demand_proxy_score=demand,
            top_competitors=top_competitors,
            notes=notes,
        )

    async def compare_areas(self, payload: CompareAreasRequest) -> CompareAreasResponse:
        brand = payload.focus_brand
        profile_a = await self.summarize_area(
            SearchPlacesRequest(
                location=payload.area_a,
                radius_m=payload.radius_m,
                categories=payload.categories or DEFAULT_CATEGORIES.copy(),
            ),
            focus_brand=brand,
        )
        profile_b = await self.summarize_area(
            SearchPlacesRequest(
                location=payload.area_b,
                radius_m=payload.radius_m,
                categories=payload.categories or DEFAULT_CATEGORIES.copy(),
            ),
            focus_brand=brand,
        )
        if profile_a.demand_proxy_score >= profile_b.demand_proxy_score:
            winner = payload.area_a
            better, other = profile_a, profile_b
        else:
            winner = payload.area_b
            better, other = profile_b, profile_a
        rationale = (
            f"{winner} shows stronger demand proxy ({better.demand_proxy_score:.1f}"
            f" vs {other.demand_proxy_score:.1f}) and saturation score"
            f" {better.saturation_score:.1f}/{other.saturation_score:.1f}."
        )
        return CompareAreasResponse(
            area_a_profile=profile_a,
            area_b_profile=profile_b,
            winner=winner,
            rationale=rationale,
        )

    async def summarize_demographics(self, payload: DemographicsRequest) -> DemographicsProfile:
        zip_code = payload.zip_code.strip() if payload.zip_code else None
        label = payload.zip_code or payload.location or "Unknown location"

        if not zip_code:
            if not payload.location:
                raise ValueError("zip_code or location is required")
            geocoded = await self.geocode(payload.location)
            zip_code = (geocoded.get("postcode") or "").strip()
            if not zip_code:
                match = re.search(r"\b(\d{5})(?:-\d{4})?\b", geocoded.get("label") or "")
                zip_code = match.group(1) if match else ""
            if not zip_code:
                raise ValueError("Could not resolve ZIP code from location")
            label = geocoded.get("label") or payload.location

        if not re.fullmatch(r"\d{5}", zip_code):
            raise ValueError("zip_code must be a 5-digit US ZIP code")

        row = await self._census_client.get_zip_demographics(zip_code)
        us_row = await self._census_client.get_us_demographics()
        benchmark = _benchmark_from_row(us_row)
        metrics = _benchmark_from_row(row)

        return DemographicsProfile(
            zip_code=zip_code,
            label=label,
            population_total=metrics.population_total,
            median_household_income=metrics.median_household_income,
            median_age=metrics.median_age,
            households_total=metrics.households_total,
            education_bachelor_plus_pct=metrics.education_bachelor_plus_pct,
            poverty_rate_pct=metrics.poverty_rate_pct,
            race_white_pct=metrics.race_white_pct,
            race_black_pct=metrics.race_black_pct,
            race_asian_pct=metrics.race_asian_pct,
            hispanic_pct=metrics.hispanic_pct,
            national_average=benchmark,
            raw=row,
        )

    async def compare_demographics(self, payload: DemographicsCompareRequest) -> DemographicsCompareResponse:
        if len(payload.queries) < 1:
            raise ValueError("queries requires at least one location or ZIP")

        profiles: list[DemographicsProfile] = []
        for query in payload.queries:
            query_value = (query or "").strip()
            if not query_value:
                continue
            req = (
                DemographicsRequest(zip_code=query_value)
                if re.fullmatch(r"\d{5}", query_value)
                else DemographicsRequest(location=query_value)
            )
            profiles.append(await self.summarize_demographics(req))

        if not profiles:
            raise ValueError("No valid queries provided")

        return DemographicsCompareResponse(
            profiles=profiles,
            national_average=profiles[0].national_average,
        )

    async def summarize_industries(self, payload: IndustryResearchRequest) -> IndustryResearchResponse:
        target_payload = payload
        if (payload.lat is None or payload.lon is None) and payload.location:
            coords = await self.geocode(payload.location)
            target_payload = payload.model_copy(update={"lat": coords["lat"], "lon": coords["lon"]})

        if target_payload.lat is None or target_payload.lon is None:
            raise ValueError("location or lat/lon is required")

        places = await self.search_places(
            SearchPlacesRequest(
                location=target_payload.location,
                lat=target_payload.lat,
                lon=target_payload.lon,
                radius_m=target_payload.radius_m,
                categories=INDUSTRY_CATEGORY_SEEDS,
            )
        )

        counts: dict[str, int] = {}
        samples: dict[str, list[str]] = {}

        for place in places:
            industry_key = _industry_from_categories(place.categories)
            counts[industry_key] = counts.get(industry_key, 0) + 1
            place_name = (place.name or "").strip()
            if place_name:
                sample_list = samples.setdefault(industry_key, [])
                if place_name not in sample_list and len(sample_list) < 3:
                    sample_list.append(place_name)

        total_places = len(places)
        ranked = sorted(counts.items(), key=lambda item: item[1], reverse=True)[: max(1, target_payload.top_n)]

        industries = [
            IndustryBucket(
                industry_key=industry_key,
                industry_label=INDUSTRY_LABELS.get(industry_key, industry_key.replace("_", " ").title()),
                place_count=count,
                share_pct=round((count / total_places) * 100, 2) if total_places else 0.0,
                sample_places=samples.get(industry_key, []),
            )
            for industry_key, count in ranked
        ]

        return IndustryResearchResponse(
            query=target_payload.location or f"{target_payload.lat},{target_payload.lon}",
            centroid=(target_payload.lat, target_payload.lon),
            radius_m=target_payload.radius_m,
            total_places=total_places,
            industries=industries,
        )

    def _reserve_credits(self, cost: int) -> None:
        projected = self._credit_estimate + cost
        ceiling = 3000 - self._geo_settings.min_remaining_credits
        if projected >= ceiling:
            raise RuntimeError("Geoapify credit guard triggered—try again tomorrow.")
        self._credit_estimate = projected
