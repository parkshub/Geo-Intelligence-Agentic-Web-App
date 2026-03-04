from __future__ import annotations

import math
from statistics import mean
from typing import Iterable

from app.models.schemas import PlaceSummary


def compute_density(count: int, radius_m: int) -> float:
    """Return POIs per square kilometer."""
    area_sq_km = math.pi * (radius_m / 1000) ** 2
    if area_sq_km == 0:
        return 0.0
    return count / area_sq_km


def saturation_score(
    *,
    brand_count: int,
    competitor_count: int,
    radius_m: int,
    target_density: float = 5.0,
) -> float:
    density = compute_density(brand_count + competitor_count, radius_m)
    score = (density / target_density) * 100
    return max(0.0, min(150.0, score))


def demand_proxy_score(
    *,
    competitors: Iterable[PlaceSummary],
    brand_count: int,
) -> float:
    popularity_scores = [p.rank_popularity for p in competitors if p.rank_popularity is not None]
    popularity_component = mean(popularity_scores) if popularity_scores else 40.0
    chain_presence = 100.0 if brand_count > 0 else 60.0
    overall = 0.6 * popularity_component + 0.4 * chain_presence
    return max(10.0, min(100.0, overall))
