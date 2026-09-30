import type { ReactNode } from "react";

type BadgeTone =
  | "neutral"
  | "navy"
  | "teal"
  | "emerald"
  | "amber"
  | "orange"
  | "red";

const TONES: Record<BadgeTone, string> = {
  neutral: "border-slate-200 bg-slate-100 text-slate-700",
  navy: "border-navy-200 bg-navy-50 text-navy-800",
  teal: "border-teal-200 bg-teal-50 text-teal-800",
  emerald: "border-emerald-200 bg-emerald-50 text-emerald-800",
  amber: "border-amber-200 bg-amber-50 text-amber-800",
  orange: "border-orange-200 bg-orange-50 text-orange-800",
  red: "border-red-200 bg-red-50 text-red-800",
};

interface BadgeProps {
  children: ReactNode;
  tone?: BadgeTone;
  className?: string;
  title?: string;
}

export default function Badge({ children, tone = "neutral", className = "", title }: BadgeProps) {
  return (
    <span
      title={title}
      className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border px-2.5 py-0.5 text-[11px] font-medium leading-4 ${TONES[tone]} ${className}`}
    >
      {children}
    </span>
  );
}