from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class PlaceSummary(BaseModel):
    place_id: str = Field(description="Stable identifier from Geoapify or Overpass composite id")
    name: str
    categories: list[str]
    brand: str | None = None
    distance_m: float
    lat: float | None = None
    lon: float | None = None
    rank_popularity: float | None = None
    opening_hours: str | None = None
    datasource: Literal["geoapify", "overpass", "foursquare"] = "geoapify"


class AreaProfile(BaseModel):
    query: str
    centroid: tuple[float, float]
    brand_count: int
    competitor_count: int
    saturation_score: float
    demand_proxy_score: float
    top_competitors: list[PlaceSummary] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class CompareAreasRequest(BaseModel):
    area_a: str
    area_b: str
    radius_m: int = 2000
    focus_brand: str | None = None
    categories: list[str] | None = None


class CompareAreasResponse(BaseModel):
    area_a_profile: AreaProfile
    area_b_profile: AreaProfile
    winner: str
    rationale: str


class DemographicsRequest(BaseModel):
    zip_code: str | None = None
    location: str | None = None


class DemographicsBenchmark(BaseModel):
    population_total: int | None = None
    median_household_income: int | None = None
    median_age: float | None = None
    households_total: int | None = None
    education_bachelor_plus_pct: float | None = None
    poverty_rate_pct: float | None = None
    race_white_pct: float | None = None
    race_black_pct: float | None = None
    race_asian_pct: float | None = None
    hispanic_pct: float | None = None


class DemographicsProfile(BaseModel):
    zip_code: str
    label: str
    population_total: int | None = None
    median_household_income: int | None = None
    median_age: float | None = None
    households_total: int | None = None
    education_bachelor_plus_pct: float | None = None
    poverty_rate_pct: float | None = None
    race_white_pct: float | None = None
    race_black_pct: float | None = None
    race_asian_pct: float | None = None
    hispanic_pct: float | None = None
    national_average: DemographicsBenchmark | None = None
    raw: dict[str, str] = Field(default_factory=dict)


class DemographicsCompareRequest(BaseModel):
    queries: list[str] = Field(default_factory=list)


class DemographicsCompareResponse(BaseModel):
    profiles: list[DemographicsProfile] = Field(default_factory=list)
    national_average: DemographicsBenchmark | None = None


class IndustryResearchRequest(BaseModel):
    location: str | None = None
    lat: float | None = None
    lon: float | None = None
    radius_m: int = 3000
    top_n: int = 8


class IndustryBucket(BaseModel):
    industry_key: str
    industry_label: str
    place_count: int
    share_pct: float
    sample_places: list[str] = Field(default_factory=list)


class IndustryResearchResponse(BaseModel):
    query: str
    centroid: tuple[float, float]
    radius_m: int
    total_places: int
    industries: list[IndustryBucket] = Field(default_factory=list)


class SearchPlacesRequest(BaseModel):
    location: str | None = None
    lat: float | None = None
    lon: float | None = None
    radius_m: int = 2000
    categories: list[str] = Field(default_factory=list)
    brand: str | None = None
    name: str | None = None

    def resolved_coordinates(self) -> tuple[float, float]:
        if self.lat is None or self.lon is None:
            raise ValueError("lat/lon must be provided when geocode is skipped")
        return self.lat, self.lon
