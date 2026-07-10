"use client";
import { useState } from "react";
import useSWR from "swr";
import { api } from "@/lib/api";
import StatusChip from "@/components/StatusChip";
import type { AlertRule, PaginatedResponse } from "@smartops/shared-types";

const fetcher = (path: string) => api.get<PaginatedResponse<AlertRule>>(path);

const SEVERITIES = ["info", "warning", "critical"] as const;
const CONDITIONS = ["gt", "lt", "gte", "lte", "eq"] as const;

export default function AlertsPage() {
  const [showModal, setShowModal] = useState(false);
  const [form, setForm] = useState({
    name: "", description: "", severity: "warning", metric: "",
    condition: "gt", threshold: "", forDuration: "5m",
  });
  const [saving, setSaving]   = useState(false);
  const [saveErr, setSaveErr] = useState("");

  const { data, error, mutate } = useSWR(`/alert-rules?page=1&pageSize=50`, fetcher, { refreshInterval: 30_000 });

  async function toggleEnabled(rule: AlertRule) {
    try {
      await api.patch(`/alert-rules/${rule.id}`, { enabled: !rule.enabled });
      await mutate();
    } catch { /* ignore */ }
  }

  async function deleteRule(id: string) {
    if (!confirm("Delete this alert rule?")) return;
    try {
      await api.delete(`/alert-rules/${id}`);
      await mutate();
    } catch { /* ignore */ }
  }

  async function createRule() {
    setSaving(true);
    setSaveErr("");
    try {
      await api.post("/alert-rules", form);
      await mutate();
      setShowModal(false);
      setForm({ name: "", description: "", severity: "warning", metric: "", condition: "gt", threshold: "", forDuration: "5m" });
    } catch (err) {
      setSaveErr(err instanceof Error ? err.message : "Failed to create rule");
    } finally {
      setSaving(false);
    }
  }

  const rules = data?.data ?? [];

  return (
    <div className="space-y-6 max-w-5xl">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-white">Alert Rules</h1>
          <p className="text-gray-500 text-sm mt-0.5">{rules.length} rules configured</p>
        </div>
        <button
          onClick={() => setShowModal(true)}
          className="flex items-center gap-2 bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium px-4 py-2 rounded-lg transition"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
          </svg>
          New Rule
        </button>
      </div>

      <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-800">
                {["Name", "Metric", "Condition", "For", "Severity", "Enabled", ""].map((h, i) => (
                  <th key={i} className={`px-4 py-3 text-gray-500 font-medium text-xs uppercase tracking-wide ${i === 0 || i === 1 ? "text-left" : "text-center"}`}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {error ? (
                <tr><td colSpan={7} className="px-4 py-8 text-center text-red-400 text-sm">{error.message}</td></tr>
              ) : rules.length === 0 ? (
                <tr><td colSpan={7} className="px-4 py-12 text-center text-gray-600 text-sm">
                  {data ? "No alert rules configured." : "Loading…"}
                </td></tr>
              ) : rules.map((rule) => (
                <tr key={rule.id} className="border-b border-gray-800/60 last:border-0 hover:bg-gray-800/40 transition">
                  <td className="px-4 py-3">
                    <div className="text-white font-medium">{rule.name}</div>
                    {rule.description && <div className="text-gray-500 text-xs mt-0.5 truncate max-w-xs">{rule.description}</div>}
                  </td>
                  <td className="px-4 py-3 font-mono text-gray-400 text-xs">{rule.metric}</td>
                  <td className="px-4 py-3 text-center text-gray-300 font-mono text-xs">
                    {rule.condition} {rule.threshold}
                  </td>
                  <td className="px-4 py-3 text-center text-gray-400 text-xs">{rule.forDuration}</td>
                  <td className="px-4 py-3 text-center">
                    <StatusChip value={rule.severity} variant={rule.severity as "critical" | "warning" | "info"} />
                  </td>
                  <td className="px-4 py-3 text-center">
                    <button
                      onClick={() => toggleEnabled(rule)}
                      className={`relative inline-flex h-5 w-9 rounded-full transition-colors ${rule.enabled ? "bg-blue-600" : "bg-gray-700"}`}
                    >
                      <span className={`absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-transform ${rule.enabled ? "translate-x-4" : "translate-x-0.5"}`} />
                    </button>
                  </td>
                  <td className="px-4 py-3 text-center">
                    <button
                      onClick={() => deleteRule(rule.id)}
                      className="text-gray-600 hover:text-red-400 transition"
                      title="Delete"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                      </svg>
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Create modal */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
          <div className="bg-gray-900 border border-gray-700 rounded-2xl w-full max-w-md shadow-2xl">
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-800">
              <h2 className="text-white font-semibold">New Alert Rule</h2>
              <button onClick={() => setShowModal(false)} className="text-gray-500 hover:text-gray-300 transition">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <div className="px-6 py-5 space-y-4">
              {saveErr && <div className="bg-red-950/60 border border-red-800/60 text-red-300 text-sm rounded-lg px-3 py-2">{saveErr}</div>}
              {[
                { label: "Rule Name", key: "name", placeholder: "High CPU" },
                { label: "Metric", key: "metric", placeholder: "smartops_cpu_usage_percent" },
                { label: "Threshold", key: "threshold", placeholder: "85" },
                { label: "For Duration", key: "forDuration", placeholder: "5m" },
              ].map(({ label, key, placeholder }) => (
                <div key={key}>
                  <label className="block text-xs font-medium text-gray-400 uppercase tracking-wide mb-1.5">{label}</label>
                  <input
                    type="text"
                    placeholder={placeholder}
                    value={form[key as keyof typeof form]}
                    onChange={(e) => setForm((f) => ({ ...f, [key]: e.target.value }))}
                    className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2.5 text-white text-sm placeholder-gray-600 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500/50 transition"
                  />
                </div>
              ))}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-gray-400 uppercase tracking-wide mb-1.5">Severity</label>
                  <select
                    value={form.severity}
                    onChange={(e) => setForm((f) => ({ ...f, severity: e.target.value }))}
                    className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2.5 text-white text-sm focus:outline-none focus:border-blue-500 transition"
                  >
                    {SEVERITIES.map((s) => <option key={s} value={s}>{s}</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-400 uppercase tracking-wide mb-1.5">Condition</label>
                  <select
                    value={form.condition}
                    onChange={(e) => setForm((f) => ({ ...f, condition: e.target.value }))}
                    className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2.5 text-white text-sm focus:outline-none focus:border-blue-500 transition"
                  >
                    {CONDITIONS.map((c) => <option key={c} value={c}>{c}</option>)}
                  </select>
                </div>
              </div>
              <div className="flex gap-3 pt-1">
                <button
                  onClick={createRule}
                  disabled={saving || !form.name.trim() || !form.metric.trim() || !form.threshold.trim()}
                  className="flex-1 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white font-medium py-2.5 rounded-lg transition text-sm"
                >
                  {saving ? "Creating…" : "Create Rule"}
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
