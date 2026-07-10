import type { LiveSpan } from "../../store/traceStore";

interface Props {
  span: LiveSpan;
  onClose: () => void;
}

export function SpanDetail({ span, onClose }: Props) {
  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
      <div className="bg-gray-900 border border-gray-700 rounded-lg w-full max-w-2xl p-6 overflow-y-auto max-h-[80vh]">
        <div className="flex justify-between items-start mb-4">
          <h2 className="text-sm font-semibold text-gray-200">Span Detail</h2>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-200 text-lg">
            ✕
          </button>
        </div>

        <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-xs">
          {[
            ["Trace ID", span.traceId],
            ["Span ID", span.spanId],
            ["Parent", span.parentSpanId || "—"],
            ["Agent", span.agentName],
            ["Event Type", span.eventType],
            ["Status", span.status],
            ["Model", span.model || "—"],
            ["Input tokens", span.inputTokens],
            ["Output tokens", span.outputTokens],
            ["Duration", span.durationMs ? `${span.durationMs}ms` : "—"],
            ["Outcome", span.outcome || "—"],
            ["Task ID", span.taskId || "—"],
          ].map(([label, value]) => (
            <>
              <dt className="text-gray-500">{label}</dt>
              <dd className="text-gray-200 break-all">{String(value)}</dd>
            </>
          ))}
        </dl>

        {span.errorMessage && (
          <div className="mt-4 p-3 bg-red-950/50 border border-red-800 rounded text-xs text-red-300">
            {span.errorMessage}
          </div>
        )}

        {Object.keys(span.attributes).length > 0 && (
          <div className="mt-4">
            <h3 className="text-xs text-gray-500 mb-2">Attributes</h3>
            <pre className="text-xs bg-gray-950 rounded p-3 overflow-x-auto">
              {JSON.stringify(span.attributes, null, 2)}
            </pre>
          </div>
        )}
      </div>
    </div>
  );
}
