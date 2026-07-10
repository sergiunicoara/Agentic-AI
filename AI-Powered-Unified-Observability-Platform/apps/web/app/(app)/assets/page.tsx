"use client";
import { useState } from "react";
import useSWR from "swr";
import { api } from "@/lib/api";
import StatusChip from "@/components/StatusChip";
import type { Asset, PaginatedResponse } from "@smartops/shared-types";

const fetcher = (path: string) => api.get<PaginatedResponse<Asset>>(path);

const ASSET_TYPES = ["server","container","database","load_balancer","cdn","storage","network"] as const;
const ENVIRONMENTS = ["production","staging","development"];

export default function AssetsPage() {
  const [page, setPage]       = useState(1);
  const [search, setSearch]   = useState("");
  const [showModal, setShowModal] = useState(false);
  const [form, setForm]       = useState({ name: "", assetType: "server", environment: "production", status: "active" });
  const [saving, setSaving]   = useState(false);
  const [saveErr, setSaveErr] = useState("");

  const params = new URLSearchParams({ page: String(page), pageSize: "15", ...(search ? { search } : {}) });
  const { data, error, mutate } = useSWR(`/assets?${params}`, fetcher, { refreshInterval: 30_000 });

  async function createAsset() {
    setSaving(true);
    setSaveErr("");
    try {
      await api.post("/assets", form);
      await mutate();
      setShowModal(false);
      setForm({ name: "", assetType: "server", environment: "production", status: "active" });
    } catch (err) {
      setSaveErr(err instanceof Error ? err.message : "Failed to create asset");
    } finally {
      setSaving(false);
    }
  }

  const assets = data?.data ?? [];
  const total  = data?.total ?? 0;
  const pages  = Math.ceil(total / 15);

  return (
    <div className="space-y-6 max-w-6xl">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-white">Assets</h1>
          <p className="text-gray-500 text-sm mt-0.5">
            {total > 0 ? `${total} assets in inventory` : "Loading…"}
          </p>
        </div>
        <button
          onClick={() => setShowModal(true)}
          className="flex items-center gap-2 bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium px-4 py-2 rounded-lg transition"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
          </svg>
          Add Asset
        </button>
      </div>

      {/* Search */}
      <div className="flex gap-3">
        <div className="relative flex-1 max-w-sm">
          <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          <input
            type="search"
            placeholder="Search assets…"
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(1); }}
            className="w-full bg-gray-800 border border-gray-700 rounded-lg pl-9 pr-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500/50 transition"
          />
        </div>
      </div>

      {/* Table */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-800">
                {["Name", "Type", "Environment", "Region", "IP Address", "Status"].map((h) => (
                  <th key={h} className={`px-4 py-3 text-gray-500 font-medium text-xs uppercase tracking-wide ${h === "Status" ? "text-right" : "text-left"}`}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {error ? (
                <tr><td colSpan={6} className="px-4 py-8 text-center text-red-400 text-sm">{error.message}</td></tr>
              ) : assets.length === 0 ? (
                <tr><td colSpan={6} className="px-4 py-12 text-center text-gray-600 text-sm">
                  {data ? "No assets found." : "Loading…"}
                </td></tr>
              ) : assets.map((a) => (
                <tr key={a.id} className="border-b border-gray-800/60 last:border-0 hover:bg-gray-800/40 transition">
                  <td className="px-4 py-3 text-white font-medium">{a.name}</td>
                  <td className="px-4 py-3 text-gray-400">{a.assetType}</td>
                  <td className="px-4 py-3 text-gray-400">{a.environment}</td>
                  <td className="px-4 py-3 text-gray-400">{a.region?.displayName ?? "—"}</td>
                  <td className="px-4 py-3 text-gray-400 font-mono text-xs">{a.ipAddress ?? "—"}</td>
                  <td className="px-4 py-3 text-right">
                    <StatusChip value={a.status} variant={a.status as "active" | "inactive" | "maintenance" | "decommissioned"} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {pages > 1 && (
          <div className="flex items-center justify-between px-4 py-3 border-t border-gray-800">
            <span className="text-xs text-gray-500">Page {page} of {pages}</span>
            <div className="flex gap-2">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
                className="px-3 py-1.5 text-xs bg-gray-800 border border-gray-700 text-gray-400 rounded-lg hover:bg-gray-700 disabled:opacity-40 disabled:cursor-not-allowed transition"
              >Prev</button>
              <button
                onClick={() => setPage((p) => Math.min(pages, p + 1))}
                disabled={page === pages}
                className="px-3 py-1.5 text-xs bg-gray-800 border border-gray-700 text-gray-400 rounded-lg hover:bg-gray-700 disabled:opacity-40 disabled:cursor-not-allowed transition"
              >Next</button>
            </div>
          </div>
        )}
      </div>

      {/* Create modal */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
          <div className="bg-gray-900 border border-gray-700 rounded-2xl w-full max-w-md shadow-2xl">
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-800">
              <h2 className="text-white font-semibold">New Asset</h2>
              <button onClick={() => setShowModal(false)} className="text-gray-500 hover:text-gray-300 transition">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <div className="px-6 py-5 space-y-4">
              {saveErr && <div className="bg-red-950/60 border border-red-800/60 text-red-300 text-sm rounded-lg px-3 py-2">{saveErr}</div>}
              {[
                { label: "Name", key: "name", type: "text", placeholder: "prod-api-01" },
              ].map(({ label, key, type, placeholder }) => (
                <div key={key}>
                  <label className="block text-xs font-medium text-gray-400 uppercase tracking-wide mb-1.5">{label}</label>
                  <input
                    type={type}
                    placeholder={placeholder}
                    value={form[key as keyof typeof form]}
                    onChange={(e) => setForm((f) => ({ ...f, [key]: e.target.value }))}
                    className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2.5 text-white text-sm placeholder-gray-600 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500/50 transition"
                  />
                </div>
              ))}
              <div>
                <label className="block text-xs font-medium text-gray-400 uppercase tracking-wide mb-1.5">Type</label>
                <select
                  value={form.assetType}
                  onChange={(e) => setForm((f) => ({ ...f, assetType: e.target.value }))}
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2.5 text-white text-sm focus:outline-none focus:border-blue-500 transition"
                >
                  {ASSET_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-400 uppercase tracking-wide mb-1.5">Environment</label>
                <select
                  value={form.environment}
                  onChange={(e) => setForm((f) => ({ ...f, environment: e.target.value }))}
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2.5 text-white text-sm focus:outline-none focus:border-blue-500 transition"
                >
                  {ENVIRONMENTS.map((e) => <option key={e} value={e}>{e}</option>)}
                </select>
              </div>
              <div className="flex gap-3 pt-1">
                <button
                  onClick={createAsset}
                  disabled={saving || !form.name.trim()}
                  className="flex-1 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white font-medium py-2.5 rounded-lg transition text-sm"
                >
                  {saving ? "Creating…" : "Create"}
                </button>
                <button
                  onClick={() => setShowModal(false)}
                  className="flex-1 bg-gray-800 hover:bg-gray-700 border border-gray-700 text-gray-300 font-medium py-2.5 rounded-lg transition text-sm"
                >
                  Cancel
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
