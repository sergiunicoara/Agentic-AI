"use client";
import { useState } from "react";
import { api } from "@/lib/api";

interface RCA {
  summary: string;
  confidence: number;
  correlatedLogs?: string[];
  correlatedTraces?: string[];
  suggestedActions?: string[];
}

interface WorkflowResult {
  runId: string;
  rca: RCA | null;
  status: string;
}

interface Props {
  result: WorkflowResult;
  onClose: () => void;
  onResolved: () => void;
}

export default function WorkflowModal({ result, onClose, onResolved }: Props) {
  const [loading, setLoading] = useState<"approve" | "reject" | null>(null);
  const [error, setError] = useState("");

  async function resume(approved: boolean) {
    setLoading(approved ? "approve" : "reject");
    setError("");
    try {
      await api.post(`/ai/workflows/${result.runId}/resume`, { approved });
      onResolved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to resume workflow");
      setLoading(null);
    }
  }

  const rca = result.rca;
  const confidencePct = rca ? Math.round(rca.confidence * 100) : 0;
  const confColor = confidencePct >= 80 ? "text-red-400" : confidencePct >= 60 ? "text-amber-400" : "text-blue-400";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
      <div className="bg-gray-900 border border-gray-700 rounded-2xl w-full max-w-2xl max-h-[90vh] overflow-y-auto shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-800">
          <div>
            <h2 className="text-white font-semibold text-base">RCA — Human Approval Required</h2>
            <p className="text-gray-500 text-xs mt-0.5 font-mono">{result.runId}</p>
          </div>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-300 transition">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {rca ? (
          <div className="px-6 py-5 space-y-5">
            {/* Confidence */}
            <div className="flex items-center gap-3">
              <div className={`text-2xl font-bold tabular-nums ${confColor}`}>{confidencePct}%</div>
              <div>
                <div className="text-gray-400 text-xs uppercase tracking-wide font-medium">AI Confidence</div>
                <div className="mt-1 h-1.5 w-40 bg-gray-800 rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full ${confidencePct >= 80 ? "bg-red-500" : confidencePct >= 60 ? "bg-amber-500" : "bg-blue-500"}`}
                    style={{ width: `${confidencePct}%` }}
                  />
                </div>
              </div>
            </div>

            {/* Summary */}
            <div>
              <h3 className="text-xs font-medium text-gray-400 uppercase tracking-wide mb-2">Root Cause Summary</h3>
              <p className="text-gray-200 text-sm leading-relaxed bg-gray-800 rounded-lg p-3 border border-gray-700">
                {rca.summary}
              </p>
            </div>

            {/* Suggested Actions */}
            {rca.suggestedActions && rca.suggestedActions.length > 0 && (
              <div>
                <h3 className="text-xs font-medium text-gray-400 uppercase tracking-wide mb-2">Suggested Actions</h3>
                <ul className="space-y-1.5">
                  {rca.suggestedActions.map((a, i) => (
                    <li key={i} className="flex items-start gap-2 text-sm text-gray-300">
                      <span className="text-blue-500 mt-0.5 flex-shrink-0">&#x25B8;</span>
                      {a}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Correlated Logs */}
            {rca.correlatedLogs && rca.correlatedLogs.length > 0 && (
              <div>
                <h3 className="text-xs font-medium text-gray-400 uppercase tracking-wide mb-2">
                  Correlated Logs <span className="text-gray-600 normal-case">({rca.correlatedLogs.length})</span>
                </h3>
                <div className="bg-gray-950 rounded-lg border border-gray-800 p-3 space-y-1 max-h-32 overflow-y-auto">
                  {rca.correlatedLogs.slice(0, 8).map((l, i) => (
                    <p key={i} className="text-xs font-mono text-gray-400 truncate">{l}</p>
                  ))}
                </div>
              </div>
            )}

            {/* Correlated Traces */}
            {rca.correlatedTraces && rca.correlatedTraces.length > 0 && (
              <div>
                <h3 className="text-xs font-medium text-gray-400 uppercase tracking-wide mb-2">
                  Correlated Traces <span className="text-gray-600 normal-case">({rca.correlatedTraces.length})</span>
                </h3>
                <div className="bg-gray-950 rounded-lg border border-gray-800 p-3 space-y-1 max-h-28 overflow-y-auto">
                  {rca.correlatedTraces.slice(0, 6).map((t, i) => (
                    <p key={i} className="text-xs font-mono text-gray-400 truncate">{t}</p>
                  ))}
                </div>
              </div>
            )}

            {error && (
              <div className="bg-red-950/60 border border-red-800/60 text-red-300 text-sm rounded-lg px-3 py-2">
                {error}
              </div>
            )}

            {/* Actions */}
            <div className="flex gap-3 pt-1">
              <button
                onClick={() => resume(true)}
                disabled={!!loading}
                className="flex-1 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white font-medium py-2.5 rounded-lg transition text-sm"
              >
                {loading === "approve" ? "Creating ticket…" : "Approve & Create Ticket"}
              </button>
              <button
                onClick={() => resume(false)}
                disabled={!!loading}
                className="flex-1 bg-gray-800 hover:bg-gray-700 disabled:opacity-50 border border-gray-700 text-gray-300 font-medium py-2.5 rounded-lg transition text-sm"
              >
                {loading === "reject" ? "Rejecting…" : "Reject"}
              </button>
            </div>
          </div>
        ) : (
          <div className="px-6 py-8 text-center text-gray-500 text-sm">
            No RCA data available for this workflow run.
          </div>
        )}
      </div>
    </div>
  );
}
