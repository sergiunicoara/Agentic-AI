import { useTraceStore } from "../store/traceStore";

export function TaskOutcomes() {
  const m = useTraceStore((s) => s.metrics);

  const cards = [
    { label: "Success", value: m.successCount, color: "text-green-400", bg: "bg-green-900/20" },
    { label: "Failure", value: m.failureCount, color: "text-red-400", bg: "bg-red-900/20" },
    { label: "Pending", value: m.pendingCount, color: "text-yellow-400", bg: "bg-yellow-900/20" },
    {
      label: "Total Tokens",
      value: m.totalInputTokens + m.totalOutputTokens,
      color: "text-blue-400",
      bg: "bg-blue-900/20",
    },
    {
      label: "Avg Latency",
      value:
        m.latencies.length > 0
          ? `${Math.round(m.latencies.reduce((a, b) => a + b, 0) / m.latencies.length)}ms`
          : "—",
      color: "text-purple-400",
      bg: "bg-purple-900/20",
    },
  ];

  return (
    <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
      {cards.map((c) => (
        <div key={c.label} className={`${c.bg} border border-gray-800 rounded-lg p-4`}>
          <div className={`text-2xl font-bold tabular-nums ${c.color}`}>{c.value}</div>
          <div className="text-xs text-gray-500 mt-1">{c.label}</div>
        </div>
      ))}
    </div>
  );
}
