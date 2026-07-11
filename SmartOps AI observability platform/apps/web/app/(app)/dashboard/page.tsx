"use client";
import { useState } from "react";
import { useMetricsStream } from "@/lib/useSSE";
import MetricCard from "@/components/MetricCard";
import clsx from "clsx";

const REGIONS = ["eu-west", "us-east", "ap-south"];

export default function DashboardPage() {
  const [activeRegion, setActiveRegion] = useState("eu-west");
  const { snapshots, history } = useMetricsStream();

  const snap = snapshots[activeRegion];
  const hist = history[activeRegion] ?? [];
  const isConnecting = Object.keys(snapshots).length === 0;

  return (
    <div className="space-y-7 max-w-6xl">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-white">Dashboard</h1>
          <p className="text-gray-500 text-sm mt-0.5">Golden signals — 5 s refresh via SSE</p>
        </div>
        <div className="flex items-center gap-2 text-xs text-gray-500">
          <span className={clsx("w-2 h-2 rounded-full", isConnecting ? "bg-amber-500 animate-pulse" : "bg-green-500")} />
          {isConnecting ? "Connecting…" : "Live"}
        </div>
      </div>

      {/* Region tabs */}
      <div className="flex gap-2 flex-wrap">
        {REGIONS.map((r) => {
          const s = snapshots[r];
          const hasAlert = s && (s.cpu > 85 || s.memory > 90 || s.p99 > 2000); // critical only
          return (
            <button
              key={r}
              onClick={() => setActiveRegion(r)}
              className={clsx(
                "flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition border",
                activeRegion === r
                  ? "bg-blue-600 border-blue-500 text-white"
                  : "bg-gray-800 border-gray-700 text-gray-400 hover:text-gray-200 hover:bg-gray-700"
              )}
            >
              {hasAlert && <span className="w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse flex-shrink-0" />}
              {r}
            </button>
          );
        })}
      </div>

      {/* Metric cards */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4 xl:grid-cols-5">
        {snap ? (
          <>
            <MetricCard
              label="CPU Usage"
              value={snap.cpu}
              history={hist.map((h) => ({ value: h.cpu }))}
              thresholds={{ warning: 80, critical: 85 }}
            />
            <MetricCard
              label="Memory Usage"
              value={snap.memory}
              history={hist.map((h) => ({ value: h.memory }))}
              thresholds={{ warning: 82, critical: 90 }}
            />
            <MetricCard
              label="P99 Latency"
              value={snap.p99}
              unit=" ms"
              history={hist.map((h) => ({ value: h.p99 }))}
              thresholds={{ warning: 1500, critical: 2000 }}
            />
            <MetricCard
              label="Error Rate"
              value={snap.errorRate}
              unit="%"
              history={hist.map((h) => ({ value: h.errorRate }))}
              thresholds={{ warning: 2, critical: 5 }}
            />
            <MetricCard
              label="Req / sec"
              value={snap.rps}
              unit=" rps"
              history={hist.map((h) => ({ value: h.rps }))}
            />
          </>
        ) : (
          Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="bg-gray-800 border border-gray-700 rounded-xl p-4 animate-pulse">
              <div className="h-3 bg-gray-700 rounded mb-4 w-20" />
              <div className="h-7 bg-gray-700 rounded mb-3 w-14" />
              <div className="h-10 bg-gray-700 rounded" />
            </div>
          ))
        )}
      </div>

      {/* All-region overview table */}
      <div>
        <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-widest mb-3">All Regions</h2>
        <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-800">
                  {["Region", "CPU", "Memory", "P99 Latency", "Err %", "RPS", "Status"].map((h) => (
                    <th
                      key={h}
                      className={clsx(
                        "px-4 py-3 text-gray-500 font-medium text-xs uppercase tracking-wide",
                        h === "Region" ? "text-left" : "text-right"
                      )}
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {REGIONS.map((r) => {
                  const s = snapshots[r];
                  const crit = s && (s.cpu > 85 || s.memory > 90 || s.p99 > 2000);
                  const warn = s && !crit && (s.cpu > 80 || s.memory > 82 || s.p99 > 1500);
                  return (
                    <tr
                      key={r}
                      className="border-b border-gray-800/60 last:border-0 hover:bg-gray-800/40 cursor-pointer transition"
                      onClick={() => setActiveRegion(r)}
                    >
                      <td className="px-4 py-3 font-medium text-white">{r}</td>
                      <td className="px-4 py-3 text-right tabular-nums text-gray-200">{s ? `${s.cpu.toFixed(1)}%` : "—"}</td>
                      <td className="px-4 py-3 text-right tabular-nums text-gray-200">{s ? `${s.memory.toFixed(1)}%` : "—"}</td>
                      <td className="px-4 py-3 text-right tabular-nums text-gray-200">{s ? `${s.p99.toFixed(0)} ms` : "—"}</td>
                      <td className="px-4 py-3 text-right tabular-nums text-gray-200">{s ? `${s.errorRate.toFixed(1)}%` : "—"}</td>
                      <td className="px-4 py-3 text-right tabular-nums text-gray-200">{s ? s.rps.toFixed(1) : "—"}</td>
                      <td className="px-4 py-3 text-right">
                        {!s ? (
                          <span className="text-gray-600 text-xs">—</span>
                        ) : crit ? (
                          <span className="inline-flex items-center gap-1.5 text-xs text-red-400 font-medium">
                            <span className="w-1.5 h-1.5 rounded-full bg-red-500" />CRITICAL
                          </span>
                        ) : warn ? (
                          <span className="inline-flex items-center gap-1.5 text-xs text-amber-400 font-medium">
                            <span className="w-1.5 h-1.5 rounded-full bg-amber-500" />WARNING
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1.5 text-xs text-green-400 font-medium">
                            <span className="w-1.5 h-1.5 rounded-full bg-green-500" />HEALTHY
                          </span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
