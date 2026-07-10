"use client";
import { useState } from "react";
import useSWR from "swr";
import { api } from "@/lib/api";
import StatusChip from "@/components/StatusChip";
import WorkflowModal from "@/components/WorkflowModal";

interface Incident {
  id: string;
  anomalyMetric: string;
  region: string;
  rcaSummary: string | null;
  confidence: number | null;
  workflowRunId: string;
  status: string;
  snowTicketId: string | null;
  createdAt: string;
  resolvedAt: string | null;
}

interface AnomalyEvent {
  id: string;
  region: string;
  host: string;
  metric: string;
  value: number;
  baseline: number;
  zScore: number;
  detectedAt: string;
}

interface WorkflowResult {
  runId: string;
  status: string;
  rca: {
    summary: string;
    confidence: number;
    correlatedLogs?: string[];
    correlatedTraces?: string[];
    suggestedActions?: string[];
  } | null;
}

const fetcher = (path: string) => api.get<{ anomalies: Incident[] }>(path);

const WATCHED = [
  { metric: "smartops_cpu_usage_percent",    label: "CPU Usage"    },
  { metric: "smartops_memory_usage_percent", label: "Memory Usage" },
];
const REGIONS = ["eu-west", "us-east", "ap-south"];

export default function AIPage() {
  const [scanning, setScanning]       = useState(false);
  const [liveAnomalies, setLive]      = useState<AnomalyEvent[]>([]);
  const [triggering, setTriggering]   = useState<string | null>(null);
  const [modal, setModal]             = useState<WorkflowResult | null>(null);
  const [triggerError, setTriggerErr] = useState("");

  const { data, mutate } = useSWR("/ai/anomalies", fetcher, { refreshInterval: 15_000 });
  const incidents = data?.anomalies ?? [];

  async function runScan() {
    setScanning(true);
    setLive([]);
    try {
      const res = await api.get<{ insights: AnomalyEvent[] }>("/ai/insights");
      setLive(res.insights);
    } catch (err) {
      console.error(err);
    } finally {
      setScanning(false);
    }
  }

  async function triggerWorkflow(metric: string, region: string) {
    const key = `${metric}:${region}`;
    setTriggering(key);
    setTriggerErr("");
    try {
      const res = await api.post<WorkflowResult>("/ai/workflows/alert-to-ticket", { metric, region });
      if (res.status === "suspended") {
        setModal(res);
      }
      await mutate();
    } catch (err) {
      setTriggerErr(err instanceof Error ? err.message : "Workflow failed");
    } finally {
      setTriggering(null);
    }
  }

  return (
    <div className="space-y-8 max-w-5xl">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-white">AI Insights</h1>
          <p className="text-gray-500 text-sm mt-0.5">Anomaly detection, RCA, and ServiceNow workflow</p>
        </div>
        <button
          onClick={runScan}
          disabled={scanning}
          className="flex items-center gap-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-60 text-white text-sm font-medium px-4 py-2 rounded-lg transition"
        >
          {scanning ? (
            <>
              <svg className="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
              </svg>
              Scanning…
            </>
          ) : (
            <>
              <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
              </svg>
              Run AI Scan
            </>
          )}
        </button>
      </div>

      {/* Live scan results */}
      {liveAnomalies.length > 0 && (
        <section>
          <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-widest mb-3">
            Live Anomalies ({liveAnomalies.length})
          </h2>
          <div className="space-y-2">
            {liveAnomalies.map((a) => (
              <div key={a.id} className="bg-red-950/20 border border-red-900/50 rounded-xl px-5 py-4 flex items-start gap-4">
                <div className="w-2 h-2 rounded-full bg-red-500 mt-1.5 flex-shrink-0 animate-pulse" />
                <div className="flex-1 min-w-0">
                  <div className="flex items-baseline gap-2 flex-wrap">
                    <span className="text-red-300 font-semibold text-sm">{a.metric}</span>
                    <span className="text-gray-500 text-xs">in {a.region}</span>
                  </div>
                  <p className="text-gray-400 text-xs mt-1">
                    Value: <span className="text-white tabular-nums">{a.value.toFixed(1)}</span> &nbsp;·&nbsp;
                    Baseline: <span className="tabular-nums">{a.baseline.toFixed(1)}</span> &nbsp;·&nbsp;
                    z-score: <span className="text-amber-400 tabular-nums">{a.zScore.toFixed(2)}</span>
                  </p>
                </div>
                <button
                  onClick={() => triggerWorkflow(a.metric, a.region)}
                  disabled={!!triggering}
                  className="flex-shrink-0 text-xs bg-blue-700 hover:bg-blue-600 disabled:opacity-50 text-white px-3 py-1.5 rounded-lg transition font-medium"
                >
                  {triggering === `${a.metric}:${a.region}` ? "Running…" : "Trigger RCA"}
                </button>
              </div>
            ))}
          </div>
          {triggerError && <p className="text-red-400 text-xs mt-2">{triggerError}</p>}
        </section>
      )}

      {liveAnomalies.length === 0 && !scanning && (
        <section>
          <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-widest mb-3">Trigger Workflow Manually</h2>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            {WATCHED.flatMap(({ metric, label }) =>
              REGIONS.map((region) => {
                const key = `${metric}:${region}`;
                return (
                  <button
                    key={key}
                    onClick={() => triggerWorkflow(metric, region)}
                    disabled={!!triggering}
                    className="bg-gray-900 border border-gray-800 hover:border-blue-700/60 hover:bg-gray-800/60 rounded-xl p-4 text-left transition group disabled:opacity-50"
                  >
                    <div className="text-xs text-gray-500 mb-1">{region}</div>
                    <div className="text-sm text-gray-300 font-medium group-hover:text-white transition">{label}</div>
                    {triggering === key && (
                      <div className="text-xs text-blue-400 mt-1.5">Running AI scan…</div>
                    )}
                  </button>
                );
              })
            )}
          </div>
          {triggerError && <p className="text-red-400 text-xs mt-3">{triggerError}</p>}
        </section>
      )}

      {/* Incidents table */}
      <section>
        <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-widest mb-3">
          Incident History ({incidents.length})
        </h2>
        <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-800">
                  {["Time", "Metric", "Region", "Confidence", "Summary", "Status", "Ticket"].map((h, i) => (
                    <th key={i} className={`px-4 py-3 text-gray-500 font-medium text-xs uppercase tracking-wide ${i <= 2 ? "text-left" : "text-center"}`}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {incidents.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="px-4 py-12 text-center text-gray-600 text-sm">
                      No incidents yet. Run an AI scan or trigger a workflow above.
                    </td>
                  </tr>
                ) : incidents.map((inc) => (
                  <tr key={inc.id} className="border-b border-gray-800/60 last:border-0 hover:bg-gray-800/40 transition">
                    <td className="px-4 py-3 text-gray-400 text-xs whitespace-nowrap">
                      {new Date(inc.createdAt).toLocaleString()}
                    </td>
                    <td className="px-4 py-3 text-gray-300 font-mono text-xs">{inc.anomalyMetric}</td>
                    <td className="px-4 py-3 text-gray-400">{inc.region}</td>
                    <td className="px-4 py-3 text-center tabular-nums text-gray-300">
                      {inc.confidence != null ? `${inc.confidence}%` : "—"}
                    </td>
                    <td className="px-4 py-3 text-gray-400 text-xs max-w-xs truncate">
                      {inc.rcaSummary ?? "—"}
                    </td>
                    <td className="px-4 py-3 text-center">
                      <StatusChip
                        value={inc.status}
                        variant={
                          inc.status === "ticketed"         ? "ticketed"  :
                          inc.status === "rejected"         ? "rejected"  :
                          inc.status === "pending_approval" ? "pending"   :
                          "info"
                        }
                      />
                    </td>
                    <td className="px-4 py-3 text-center font-mono text-xs text-gray-500">
                      {inc.snowTicketId ?? "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      {/* Workflow approval modal */}
      {modal && (
        <WorkflowModal
          result={modal}
          onClose={() => setModal(null)}
          onResolved={() => { setModal(null); void mutate(); }}
        />
      )}
    </div>
  );
}
