import { useState } from "react";
import { useTraceStore } from "../../store/traceStore";
import type { LiveSpan } from "../../store/traceStore";
import { SpanRow } from "./SpanRow";
import { SpanDetail } from "./SpanDetail";

export function TraceViewer() {
  const events = useTraceStore((s) => s.events);
  const clearEvents = useTraceStore((s) => s.clearEvents);
  const [selected, setSelected] = useState<LiveSpan | null>(null);

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-semibold text-gray-300">
          Live Events{" "}
          <span className="ml-2 text-xs text-gray-500 font-normal">{events.length} buffered</span>
        </h2>
        <button
          onClick={clearEvents}
          className="text-xs text-gray-500 hover:text-gray-300 transition-colors"
        >
          Clear
        </button>
      </div>

      <div className="overflow-auto rounded border border-gray-800 flex-1">
        <table className="w-full text-left">
          <thead className="sticky top-0 bg-gray-900">
            <tr className="border-b border-gray-700">
              {["Time", "Event", "Agent", "Trace ID", "Tokens", "Duration", "Status"].map((h) => (
                <th
                  key={h}
                  className="py-2 px-3 text-[10px] uppercase tracking-wider text-gray-500 font-medium"
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {events.length === 0 ? (
              <tr>
                <td colSpan={7} className="py-12 text-center text-xs text-gray-600">
                  Waiting for agent events… Run the SDK example to see live data.
                </td>
              </tr>
            ) : (
              events.map((ev, i) => (
                <SpanRow key={`${ev.spanId}-${i}`} span={ev} onClick={setSelected} />
              ))
            )}
          </tbody>
        </table>
      </div>

      {selected && <SpanDetail span={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}
