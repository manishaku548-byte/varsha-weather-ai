"use client";

import dynamic from "next/dynamic";
import { Skeleton } from "./Skeleton";
import type { District } from "@/types/api";

export interface DistrictMapProps {
  districts: District[];
  selectedDistrictId: string | null;
  selectedRiskLabel?: string | null;
  selectedRainfallMm?: number | null;
  onSelectDistrict: (districtId: string) => void;
}

// react-leaflet must never render on the server (window APIs); load it lazily.
const DistrictMapInner = dynamic(() => import("./DistrictMapInner"), {
  ssr: false,
  loading: () => <Skeleton className="h-[360px] w-full" />,
});

export default function DistrictMap(props: DistrictMapProps) {
  return <DistrictMapInner {...props} />;
}