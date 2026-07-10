"use client";
import clsx from "clsx";
import SparkLine from "./SparkLine";

interface Props {
  label: string;
  value: number;
  unit?: string;
  history: { value: number }[];
  thresholds?: { warning: number; critical: number };
}

function severity(value: number, t?: { warning: number; critical: number }) {
  if (!t) return "normal";
  if (value >= t.critical) return "critical";
  if (value >= t.warning) return "warning";
  return "normal";
}

export default function MetricCard({ label, value, unit = "%", history, thresholds }: Props) {
  const sev = severity(value, thresholds);
  const color = sev === "critical" ? "#ef4444" : sev === "warning" ? "#f59e0b" : "#3b82f6";

  return (
    <div className={clsx(
      "bg-gray-800 border rounded-xl p-4 transition",
      sev === "critical" ? "border-red-800/60"  :
      sev === "warning"  ? "border-amber-800/60" :
      "border-gray-700"
    )}>
      <div className="flex items-start justify-between mb-1">
        <span className="text-gray-400 text-xs font-medium uppercase tracking-wide">{label}</span>
        <span className={clsx("text-xs font-semibold px-1.5 py-0.5 rounded",
          sev === "critical" ? "bg-red-950 text-red-400"    :
          sev === "warning"  ? "bg-amber-950 text-amber-400" :
          "bg-blue-950 text-blue-400"
        )}>
          {sev === "critical" ? "CRIT" : sev === "warning" ? "WARN" : "OK"}
        </span>
      </div>
      <div className="text-2xl font-bold text-white mb-2 tabular-nums">
        {value.toFixed(1)}
        <span className="text-gray-500 text-sm font-normal ml-0.5">{unit}</span>
      </div>
      <SparkLine data={history} color={color} />
    </div>
  );
}
