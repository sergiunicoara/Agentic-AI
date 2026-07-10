import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import { useTraceStore } from "../store/traceStore";

export function TokenUsageChart() {
  const events = useTraceStore((s) => s.events);

  // Aggregate tokens per agent for the last 50 events
  const agg: Record<string, { input: number; output: number }> = {};
  events.slice(0, 50).forEach((ev) => {
    if (!agg[ev.agentName]) agg[ev.agentName] = { input: 0, output: 0 };
    agg[ev.agentName].input += ev.inputTokens;
    agg[ev.agentName].output += ev.outputTokens;
  });

  const data = Object.entries(agg).map(([name, v]) => ({
    name,
    input: v.input,
    output: v.output,
  }));

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
      <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">
        Token Usage by Agent
      </h3>
      <ResponsiveContainer width="100%" height={200}>
        <BarChart data={data} margin={{ top: 4, right: 8, bottom: 4, left: 0 }} style={{ background: "transparent" }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
          <XAxis dataKey="name" tick={{ fontSize: 10, fill: "#6b7280" }} />
          <YAxis tick={{ fontSize: 10, fill: "#6b7280" }} />
          <Tooltip
            contentStyle={{ background: "#111827", border: "1px solid #374151", fontSize: 11 }}
          />
          <Legend wrapperStyle={{ fontSize: 11 }} />
          <Bar dataKey="input" fill="#0ea5e9" name="Input" radius={[2, 2, 0, 0]} />
          <Bar dataKey="output" fill="#8b5cf6" name="Output" radius={[2, 2, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
