import type { LiveSpan } from "../../store/traceStore";

const EVENT_COLORS: Record<string, string> = {
  span_start: "text-blue-400",
  span_end: "text-green-400",
  llm_call: "text-purple-400",
  tool_call: "text-yellow-400",
  error: "text-red-400",
  trace_summary: "text-sky-400",
};

interface Props {
  span: LiveSpan;
  onClick: (span: LiveSpan) => void;
}

export function SpanRow({ span, onClick }: Props) {
  const color = EVENT_COLORS[span.eventType] ?? "text-gray-400";
  const ts = new Date(span.timestampMs).toISOString().slice(11, 23);

  return (
    <tr
      className="border-b border-gray-800/50 hover:bg-gray-800/40 cursor-pointer transition-colors"
      onClick={() => onClick(span)}
    >
      <td className="py-1.5 px-3 text-[11px] text-gray-500 font-mono tabular-nums">{ts}</td>
      <td className={`py-1.5 px-3 text-[11px] font-mono ${color}`}>{span.eventType}</td>
      <td className="py-1.5 px-3 text-[11px] text-gray-300 font-mono">{span.agentName}</td>
      <td className="py-1.5 px-3 text-[11px] text-gray-400 font-mono truncate max-w-[140px]">
        {span.traceId.slice(0, 8)}
      </td>
      <td className="py-1.5 px-3 text-[11px] text-gray-400 font-mono tabular-nums">
        {span.inputTokens + span.outputTokens > 0
          ? `${span.inputTokens}↑ ${span.outputTokens}↓`
          : "—"}
      </td>
      <td className="py-1.5 px-3 text-[11px] text-gray-400 font-mono tabular-nums">
        {span.durationMs > 0 ? `${span.durationMs}ms` : "—"}
      </td>
      <td className="py-1.5 px-3">
        <span
          className={`inline-block px-1.5 py-0.5 rounded text-[10px] font-medium ${
            span.status === "error"
              ? "bg-red-900/50 text-red-400"
              : "bg-green-900/30 text-green-400"
          }`}
        >
          {span.status}
        </span>
      </td>
    </tr>
  );
}
