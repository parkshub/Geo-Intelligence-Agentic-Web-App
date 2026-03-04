"use client";

import { CircleMarker, MapContainer, Popup, TileLayer } from "react-leaflet";

type CompetitorPoint = {
  name: string;
  lat: number;
  lon: number;
};

type InteractiveAreaMapProps = {
  centroid: [number, number];
  query: string;
  competitors: CompetitorPoint[];
};

export default function InteractiveAreaMap({
  centroid,
  query,
  competitors,
}: InteractiveAreaMapProps) {
  return (
    <MapContainer
      center={centroid}
      zoom={13}
      className="h-full w-full"
      scrollWheelZoom={false}
      key={`${query}-${centroid[0]}-${centroid[1]}`}
    >
      <TileLayer
        attribution="&copy; OpenStreetMap contributors"
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <CircleMarker
        center={centroid}
        radius={8}
        pathOptions={{ color: "#f97316", fillColor: "#f97316", fillOpacity: 0.85 }}
      >
        <Popup>{query}</Popup>
      </CircleMarker>
      {competitors.map((competitor, index) => (
        <CircleMarker
          key={`${competitor.name}-${index}`}
          center={[competitor.lat, competitor.lon]}
          radius={5}
          pathOptions={{ color: "#60a5fa", fillColor: "#60a5fa", fillOpacity: 0.75 }}
        >
          <Popup>{competitor.name}</Popup>
        </CircleMarker>
      ))}
    </MapContainer>
  );
}
