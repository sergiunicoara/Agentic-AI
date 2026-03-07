import { useEffect, useState } from "react";
import { listTraces, getTrace } from "../api/restClient";
import type { TraceOut, TraceDetailOut } from "../api/restClient";

export function TracesPage() {
  const [traces, setTraces] = useState<TraceOut[]>([]);
  const [selected, setSelected] = useState<TraceDetailOut | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    listTraces({ limit: 100 })
      .then(setTraces)
      .finally(() => setLoading(false));
  }, []);

  async function openTrace(id: string) {
    const detail = await getTrace(id);
    setSelected(detail);
  }

  return (
    <div>
      <h1 className="text-sm font-semibold text-gray-300 mb-4">Trace History</h1>

      {loading ? (
        <p className="text-xs text-gray-500">Loading…</p>
      ) : (
        <div className="overflow-auto rounded border border-gray-800">
          <table className="w-full text-left text-xs">
            <thead className="bg-gray-900 border-b border-gray-700">
              <tr>
                {["Trace ID", "Agent", "Task", "Outcome", "Created"].map((h) => (
                  <th key={h} className="py-2 px-3 text-[10px] uppercase tracking-wider text-gray-500 font-medium">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {traces.map((t) => (
                <tr
                  key={t.id}
                  className="border-b border-gray-800/50 hover:bg-gray-800/40 cursor-pointer"
                  onClick={() => openTrace(t.id)}
                >
                  <td className="py-2 px-3 text-gray-400 font-mono">{t.id.slice(0, 12)}…</td>
                  <td className="py-2 px-3 text-gray-300">{t.agent_name}</td>
                  <td className="py-2 px-3 text-gray-400">{t.task_id ?? "—"}</td>
                  <td className="py-2 px-3">
                    <span className={t.outcome === "success" ? "text-green-400" : t.outcome === "failure" ? "text-red-400" : "text-yellow-400"}>
                      {t.outcome}
                    </span>
                  </td>
                  <td className="py-2 px-3 text-gray-500">{new Date(t.created_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {selected && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-gray-900 border border-gray-700 rounded-lg w-full max-w-3xl p-6 max-h-[80vh] overflow-y-auto">
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-sm font-semibold text-gray-200">Trace: {selected.id}</h2>
              <button onClick={() => setSelected(null)} className="text-gray-500 hover:text-gray-200">✕</button>
            </div>
            <p className="text-xs text-gray-500 mb-4">{selected.spans.length} spans</p>
            <div className="space-y-1">
              {selected.spans.map((s) => (
                <div key={s.id} className="flex items-center gap-3 text-[11px] font-mono border-b border-gray-800/50 py-1">
                  <span className="text-gray-500 w-28 shrink-0">{s.event_type}</span>
                  <span className="text-gray-400">{s.model ?? "—"}</span>
                  <span className="text-gray-500">{s.duration_ms}ms</span>
                  <span className="text-blue-400">{s.input_tokens}↑</span>
                  <span className="text-purple-400">{s.output_tokens}↓</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
