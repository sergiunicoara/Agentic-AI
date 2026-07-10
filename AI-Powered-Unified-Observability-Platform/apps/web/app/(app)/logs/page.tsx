"use client";
import { useState, type FormEvent } from "react";
import { api } from "@/lib/api";
import clsx from "clsx";

interface LogHit {
  id: string;
  timestamp: string;
  message: string;
  logLevel: string;
  service: string;
  region: string;
  traceId?: string;
  spanId?: string;
}

interface LogResponse {
  hits: LogHit[];
  total: number;
}

const LEVELS = ["all", "error", "warn", "info", "debug"] as const;
const LEVEL_COLOR: Record<string, string> = {
  error: "text-red-400",
  warn:  "text-amber-400",
  info:  "text-blue-400",
  debug: "text-gray-500",
};

export default function LogsPage() {
  const [query, setQuery]       = useState("");
  const [level, setLevel]       = useState<typeof LEVELS[number]>("all");
  const [result, setResult]     = useState<LogResponse | null>(null);
  const [loading, setLoading]   = useState(false);
  const [error, setError]       = useState("");

  async function search(e?: FormEvent) {
    e?.preventDefault();
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams({ q: query || "*", size: "50" });
      if (level !== "all") params.set("level", level);
      const res = await api.get<LogResponse>(`/logs/search?${params}`);
      setResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search failed");
      setResult(null);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-6 max-w-6xl">
      <div>
        <h1 className="text-xl font-bold text-white">Log Explorer</h1>
        <p className="text-gray-500 text-sm mt-0.5">Full-text search via Elasticsearch</p>
      </div>

      {/* Search bar */}
      <form onSubmit={search} className="flex gap-3">
        <div className="relative flex-1">
          <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          <input
            type="search"
            placeholder="Search logs… (e.g. error OOM, timeout, trace ID)"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="w-full bg-gray-800 border border-gray-700 rounded-lg pl-9 pr-3 py-2.5 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500/50 transition font-mono"
          />
        </div>

        {/* Level filter */}
        <div className="flex bg-gray-800 border border-gray-700 rounded-lg overflow-hidden">
          {LEVELS.map((l) => (
            <button
              key={l}
              type="button"
              onClick={() => setLevel(l)}
              className={clsx(
                "px-3 py-2 text-xs font-medium transition border-r border-gray-700 last:border-0",
                level === l ? "bg-gray-700 text-white" : "text-gray-500 hover:text-gray-300 hover:bg-gray-700/50"
              )}
            >
              {l}
            </button>
          ))}
        </div>

        <button
          type="submit"
          disabled={loading}
          className="bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-sm font-medium px-5 py-2.5 rounded-lg transition"
        >
          {loading ? "…" : "Search"}
        </button>
      </form>

      {/* Error */}
      {error && (
        <div className="bg-red-950/60 border border-red-800/60 text-red-300 text-sm rounded-lg px-4 py-3">
          {error}
        </div>
      )}

      {/* Results */}
      {result && (
        <div>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-widest">
              {result.total.toLocaleString()} result{result.total !== 1 ? "s" : ""}
            </h2>
            {result.hits.length > 0 && (
              <span className="text-xs text-gray-600">Showing {result.hits.length}</span>
            )}
          </div>

          {result.hits.length === 0 ? (
            <div className="bg-gray-900 border border-gray-800 rounded-xl px-4 py-12 text-center text-gray-600 text-sm">
              No logs matched your query.
            </div>
          ) : (
            <div className="bg-gray-950 border border-gray-800 rounded-xl overflow-hidden font-mono text-xs">
              {result.hits.map((hit, i) => (
                <div
                  key={hit.id ?? i}
                  className="flex gap-3 px-4 py-2.5 border-b border-gray-800/60 last:border-0 hover:bg-gray-900/80 transition"
                >
                  <span className="text-gray-600 flex-shrink-0 w-36 truncate">
                    {new Date(hit.timestamp).toLocaleTimeString()}
                  </span>
                  <span className={clsx("flex-shrink-0 w-12 uppercase font-semibold", LEVEL_COLOR[hit.logLevel] ?? "text-gray-400")}>
                    {hit.logLevel}
                  </span>
                  <span className="text-gray-500 flex-shrink-0 w-28 truncate">{hit.service}</span>
                  <span className="text-gray-500 flex-shrink-0 w-20 truncate">{hit.region}</span>
                  <span className="text-gray-300 flex-1 truncate">{hit.message}</span>
                  {hit.traceId && (
                    <span className="text-gray-600 flex-shrink-0 truncate w-28" title={hit.traceId}>
                      {hit.traceId.slice(0, 12)}…
                    </span>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {!result && !loading && !error && (
        <div className="border border-dashed border-gray-800 rounded-xl px-4 py-16 text-center">
          <p className="text-gray-600 text-sm">Enter a search query and press Search to explore logs from Elasticsearch.</p>
          <div className="mt-4 flex flex-wrap justify-center gap-2">
            {["error", "OOM", "timeout", "connection refused", "5xx"].map((s) => (
              <button
                key={s}
                onClick={() => { setQuery(s); }}
                className="text-xs bg-gray-800 text-gray-400 hover:text-gray-200 border border-gray-700 px-2.5 py-1 rounded-md transition"
              >
                {s}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
