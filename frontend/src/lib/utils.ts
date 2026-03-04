import type {
  AreaProfile,
  DemographicsBenchmark,
  DemographicsProfile,
  ToolCall,
} from "./types";

export const API_BASE =
  process.env.NEXT_PUBLIC_AGENT_API_BASE ?? "http://localhost:8002";

export const STATIC_MAP_KEY = process.env.NEXT_PUBLIC_GEOAPIFY_STATIC_KEY;

export function uuid() {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return Math.random().toString(36).slice(2);
}

export function formatTimestamp(date = new Date()): string {
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export function bucketToolCalls(toolCalls: ToolCall[]) {
  const profiles: AreaProfile[] = [];
  const searchDerivedProfiles: AreaProfile[] = [];
  const demographicsProfiles: DemographicsProfile[] = [];
  let demographicsNational: DemographicsBenchmark | null = null;
  let comparison: unknown = null;

  const toNumber = (value: unknown): number | null =>
    typeof value === "number" && Number.isFinite(value) ? value : null;

  const profileFromSearchPlaces = (call: ToolCall): AreaProfile | null => {
    if (call.tool !== "search_places" || !Array.isArray(call.observation)) {
      return null;
    }
    const places = call.observation.filter(
      (item): item is Record<string, unknown> =>
        !!item && typeof item === "object" && !Array.isArray(item),
    );
    if (places.length === 0) {
      return null;
    }

    const points = places
      .map((place) => ({
        lat: toNumber(place.lat),
        lon: toNumber(place.lon),
      }))
      .filter(
        (point): point is { lat: number; lon: number } =>
          point.lat !== null && point.lon !== null,
      );

    const centroid: [number, number] =
      points.length > 0
        ? [
            points.reduce((sum, point) => sum + point.lat, 0) / points.length,
            points.reduce((sum, point) => sum + point.lon, 0) / points.length,
          ]
        : [34.0522, -118.2437];

    const query =
      typeof call.input?.location === "string" && call.input.location.trim()
        ? call.input.location
        : "Search results";

    const top_competitors = places
      .slice(0, 20)
      .map((place) => ({
        name:
          (typeof place.name === "string" && place.name) ||
          (typeof place.formatted === "string" && place.formatted) ||
          "Unnamed place",
        brand: typeof place.brand === "string" ? place.brand : null,
        distance_m: toNumber(place.distance_m) ?? undefined,
        lat: toNumber(place.lat),
        lon: toNumber(place.lon),
        rank_popularity: toNumber(place.rank_popularity) ?? undefined,
      }));

    return {
      query,
      centroid,
      brand_count: 0,
      competitor_count: places.length,
      saturation_score: 0,
      demand_proxy_score: 0,
      top_competitors,
      notes: ["Rendered from search results."],
    };
  };

  toolCalls.forEach((call) => {
    if (
      call.observation &&
      typeof call.observation === "object" &&
      "competitor_count" in call.observation
    ) {
      profiles.push(call.observation as AreaProfile);
    }
    if (call.tool === "compare_areas") {
      comparison = call.observation;
      if (
        call.observation &&
        typeof call.observation === "object" &&
        "area_a_profile" in call.observation
      ) {
        const obs = call.observation as {
          area_a_profile?: AreaProfile;
          area_b_profile?: AreaProfile;
        };
        if (obs.area_a_profile) profiles.push(obs.area_a_profile);
        if (obs.area_b_profile) profiles.push(obs.area_b_profile);
      }
    }
    if (
      call.tool === "get_demographics" &&
      call.observation &&
      typeof call.observation === "object" &&
      "zip_code" in call.observation
    ) {
      const profile = call.observation as DemographicsProfile;
      demographicsProfiles.push(profile);
      demographicsNational = profile.national_average ?? demographicsNational;
    }
    if (
      call.tool === "compare_demographics" &&
      call.observation &&
      typeof call.observation === "object" &&
      "profiles" in call.observation
    ) {
      const obs = call.observation as {
        profiles?: DemographicsProfile[];
        national_average?: DemographicsBenchmark | null;
      };
      if (Array.isArray(obs.profiles)) {
        demographicsProfiles.push(...obs.profiles);
      }
      if (obs.national_average) {
        demographicsNational = obs.national_average;
      }
    }

    const searchProfile = profileFromSearchPlaces(call);
    if (searchProfile) {
      searchDerivedProfiles.push(searchProfile);
    }
  });

  const isSearchDerived = (profile: AreaProfile) =>
    profile.notes?.includes("Rendered from search results.") ?? false;

  const mergedByQuery = new Map<string, AreaProfile>();
  [...profiles, ...searchDerivedProfiles].forEach((profile) => {
    const key = profile.query;
    const current = mergedByQuery.get(key);
    if (!current) {
      mergedByQuery.set(key, profile);
      return;
    }
    // Prefer real summarize/compare profiles over search-derived placeholders.
    if (isSearchDerived(current) && !isSearchDerived(profile)) {
      mergedByQuery.set(key, profile);
    }
  });

  return {
    profiles: Array.from(mergedByQuery.values()),
    comparison,
    demographicsProfiles,
    demographicsNational,
  };
}

export function estimateCredits(toolCalls: ToolCall[]): number {
  return toolCalls.reduce((acc, call) => {
    if (call.tool === "search_places") return acc + 5;
    if (call.tool === "summarize_area") return acc + 3;
    if (call.tool === "compare_areas") return acc + 6;
    return acc + 1;
  }, 0);
}

export function buildStaticMapUrl(
  centroid: [number, number],
  label: string,
  zoom = 13,
) {
  if (!STATIC_MAP_KEY) return null;
  const [lat, lon] = centroid;
  return `https://maps.geoapify.com/v1/staticmap?style=klokantech-basic&width=600&height=280&center=lonlat:${lon},${lat}&zoom=${zoom}&marker=lonlat:${lon},${lat};type:material;color:%23ff6b35;size:small&apiKey=${STATIC_MAP_KEY}&text=${encodeURIComponent(label)}`;
}

export function downloadWorksheet(markdown: string, filename: string) {
  const blob = new Blob([markdown], { type: "text/markdown" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

export function downloadTextFile(content: string, filename: string, mimeType: string) {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}
