export type Role = "user" | "assistant";

export interface ChatMessage {
  id: string;
  role: Role;
  content: string;
  timestamp: string;
  localOnly?: boolean;
}

export interface ToolCall {
  tool: string;
  input: Record<string, unknown>;
  observation: unknown;
  log?: string;
}

export interface AreaProfile {
  query: string;
  centroid: [number, number];
  brand_count: number;
  competitor_count: number;
  saturation_score: number;
  demand_proxy_score: number;
  top_competitors: Array<{
    name: string;
    brand?: string | null;
    distance_m?: number;
    lat?: number | null;
    lon?: number | null;
    rank_popularity?: number;
  }>;
  notes?: string[];
}

export interface CompareAreasPayload {
  area_a_profile: AreaProfile;
  area_b_profile: AreaProfile;
  winner: string;
  rationale: string;
}

export interface DemographicsBenchmark {
  population_total?: number | null;
  median_household_income?: number | null;
  median_age?: number | null;
  households_total?: number | null;
  education_bachelor_plus_pct?: number | null;
  poverty_rate_pct?: number | null;
  race_white_pct?: number | null;
  race_black_pct?: number | null;
  race_asian_pct?: number | null;
  hispanic_pct?: number | null;
}

export interface DemographicsProfile {
  zip_code: string;
  label: string;
  population_total?: number | null;
  median_household_income?: number | null;
  median_age?: number | null;
  households_total?: number | null;
  education_bachelor_plus_pct?: number | null;
  poverty_rate_pct?: number | null;
  race_white_pct?: number | null;
  race_black_pct?: number | null;
  race_asian_pct?: number | null;
  hispanic_pct?: number | null;
  national_average?: DemographicsBenchmark | null;
}

export interface DemographicsComparison {
  profiles: DemographicsProfile[];
  national_average?: DemographicsBenchmark | null;
}
