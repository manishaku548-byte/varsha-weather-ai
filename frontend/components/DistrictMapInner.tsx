"use client";

import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { Circle, MapContainer, Marker, TileLayer, Tooltip } from "react-leaflet";
import type { District } from "@/types/api";

interface DistrictMapInnerProps {
  districts: District[];
  selectedDistrictId: string | null;
  selectedRiskLabel?: string | null;
  onSelectDistrict: (districtId: string) => void;
}

function makePin(
  selected: boolean,
  hasForecast: boolean,
  initial: string,
): L.DivIcon {
  const background = selected ? "#0d9488" : hasForecast ? "#2a5f9e" : "#94a3b8";
  const ring = selected ? "0 0 0 3px rgba(13,148,136,0.28)" : "0 1px 3px rgba(10,35,66,0.35)";
  return L.divIcon({
    className: "varsha-district-pin",
    html: `<div style="width:34px;height:34px;border-radius:50%;background:${background};color:#fff;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:12px;border:2px solid #fff;box-shadow:${ring};">${initial}</div>`,
    iconSize: [34, 34],
    iconAnchor: [17, 17],
    popupAnchor: [0, -20],
  });
}

export default function DistrictMapInner({
  districts,
  selectedDistrictId,
  selectedRiskLabel,
  onSelectDistrict,
}: DistrictMapInnerProps) {
  const center: [number, number] = [26.3, 81.9];

  return (
    <div className="relative">
      <MapContainer
        center={center}
        zoom={7}
        minZoom={6}
        maxZoom={12}
        scrollWheelZoom={false}
        className="z-0 h-[360px] w-full rounded-lg border border-slate-200"
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>'
          url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
          maxZoom={20}
        />
        {districts.map((district) => {
          const selected = district.district_id === selectedDistrictId;
          const hasForecast = selected && Boolean(selectedRiskLabel);
          const icon = makePin(selected, hasForecast, district.district_name.charAt(0));
          return (
            <div key={district.district_id}>
              {selected ? (
                <Circle
                  center={[district.latitude, district.longitude]}
                  radius={14000}
                  pathOptions={{
                    color: "#0d9488",
                    weight: 2,
                    fillColor: "#0d9488",
                    fillOpacity: 0.06,
                  }}
                />
              ) : null}
              <Marker
                position={[district.latitude, district.longitude]}
                icon={icon}
                eventHandlers={{
                  click: () => onSelectDistrict(district.district_id),
                }}
              >
                {selected ? (
                  <Tooltip direction="top" offset={[0, -22]} permanent opacity={1}>
                    <span className="text-xs font-semibold">
                      {district.district_name}
                      {hasForecast
                        ? ` · ${selectedRiskLabel ?? "No forecast"}`
                        : " · no active forecast"}
                    </span>
                  </Tooltip>
                ) : (
                  <Tooltip direction="top" offset={[0, -22]}>
                    <span className="text-xs">
                      {district.district_name} — no active forecast for the current
                      selection
                    </span>
                  </Tooltip>
                )}
              </Marker>
            </div>
          );
        })}
      </MapContainer>

      <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-slate-500">
        <span className="inline-flex items-center gap-1.5">
          <span className="inline-block h-3 w-3 rounded-full border-2 border-white" style={{ backgroundColor: "#0d9488" }} aria-hidden="true" />
          Selected district (risk label from the active forecast)
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="inline-block h-3 w-3 rounded-full border-2 border-white" style={{ backgroundColor: "#94a3b8" }} aria-hidden="true" />
          No active forecast for this selection
        </span>
        <span className="ml-auto">Prototype district overview — not an official warning map.</span>
      </div>
    </div>
  );
}