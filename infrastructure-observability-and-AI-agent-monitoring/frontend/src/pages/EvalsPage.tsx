import { useEffect, useState } from "react";
import { listEvals, createEval } from "../api/restClient";
import type { EvalRunOut } from "../api/restClient";

export function EvalsPage() {
  const [runs, setRuns] = useState<EvalRunOut[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [traceId, setTraceId] = useState("");

  useEffect(() => {
    listEvals().then(setRuns);
  }, []);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    const run = await createEval({ name, trace_id: traceId || undefined });
    setRuns([run, ...runs]);
    setShowForm(false);
    setName("");
    setTraceId("");
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-sm font-semibold text-gray-300">Evaluation Runs</h1>
        <button
          onClick={() => setShowForm(true)}
          className="text-xs px-3 py-1.5 bg-brand-500 hover:bg-brand-700 text-white rounded transition-colors"
        >
          + New Run
        </button>
      </div>

      {showForm && (
        <form onSubmit={handleCreate} className="mb-6 bg-gray-900 border border-gray-700 rounded-lg p-4 flex gap-3 items-end">
          <div>
            <label className="block text-xs text-gray-500 mb-1">Name</label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              className="px-2 py-1 bg-gray-800 border border-gray-700 rounded text-sm text-gray-100 focus:outline-none focus:border-brand-500"
            />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">Trace ID (optional)</label>
            <input
              value={traceId}
              onChange={(e) => setTraceId(e.target.value)}
              className="px-2 py-1 bg-gray-800 border border-gray-700 rounded text-sm text-gray-100 focus:outline-none focus:border-brand-500"
              placeholder="uuid"
            />
          </div>
          <button type="submit" className="text-xs px-3 py-1.5 bg-green-700 hover:bg-green-600 text-white rounded">Create</button>
          <button type="button" onClick={() => setShowForm(false)} className="text-xs text-gray-500 hover:text-gray-300">Cancel</button>
        </form>
      )}

      <div className="overflow-auto rounded border border-gray-800">
        <table className="w-full text-left text-xs">
          <thead className="bg-gray-900 border-b border-gray-700">
            <tr>
              {["Name", "Trace", "Status", "Created by"].map((h) => (
                <th key={h} className="py-2 px-3 text-[10px] uppercase tracking-wider text-gray-500 font-medium">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {runs.map((r) => (
              <tr key={r.id} className="border-b border-gray-800/50">
                <td className="py-2 px-3 text-gray-300">{r.name}</td>
                <td className="py-2 px-3 text-gray-500 font-mono">{r.trace_id?.slice(0, 8) ?? "—"}</td>
                <td className="py-2 px-3 text-yellow-400">{r.status}</td>
                <td className="py-2 px-3 text-gray-500 font-mono">{r.created_by.slice(0, 8)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
