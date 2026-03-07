import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { useTraceStore } from "../store/traceStore";

export function LatencyChart() {
  const latencies = useTraceStore((s) => s.metrics.latencies);

  const data = latencies.slice(-30).map((ms, i) => ({ i: i + 1, ms }));

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
      <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">
        Span Latency (last 30)
      </h3>
      <ResponsiveContainer width="100%" height={200}>
        <LineChart data={data} margin={{ top: 4, right: 8, bottom: 4, left: 0 }} style={{ background: "transparent" }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
          <XAxis dataKey="i" tick={{ fontSize: 10, fill: "#6b7280" }} />
          <YAxis unit="ms" tick={{ fontSize: 10, fill: "#6b7280" }} />
          <Tooltip
            contentStyle={{ background: "#111827", border: "1px solid #374151", fontSize: 11 }}
            formatter={(v: number) => [`${v}ms`, "Latency"]}
          />
          <Line
            type="monotone"
            dataKey="ms"
            stroke="#0ea5e9"
            dot={false}
            strokeWidth={1.5}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
