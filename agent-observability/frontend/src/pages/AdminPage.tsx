import { useEffect, useState } from "react";
import { listUsers, getAuditLog } from "../api/restClient";
import type { UserOut } from "../api/restClient";

interface Props {
  role: string | null;
}

export function AdminPage({ role }: Props) {
  const [users, setUsers] = useState<UserOut[]>([]);
  const [audit, setAudit] = useState<any[]>([]);
  const [tab, setTab] = useState<"users" | "audit">("users");

  useEffect(() => {
    if (role !== "admin") return;
    listUsers().then(setUsers);
    getAuditLog().then(setAudit);
  }, [role]);

  if (role !== "admin") {
    return (
      <div className="flex items-center justify-center h-64">
        <p className="text-sm text-gray-500">Admin access required.</p>
      </div>
    );
  }

  return (
    <div>
      <h1 className="text-sm font-semibold text-gray-300 mb-4">Administration</h1>

      <div className="flex gap-2 mb-4">
        {(["users", "audit"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`text-xs px-3 py-1.5 rounded transition-colors ${
              tab === t ? "bg-brand-700 text-white" : "bg-gray-800 text-gray-400 hover:bg-gray-700"
            }`}
          >
            {t === "users" ? "Users" : "Audit Log"}
          </button>
        ))}
      </div>

      {tab === "users" && (
        <div className="overflow-auto rounded border border-gray-800">
          <table className="w-full text-left text-xs">
            <thead className="bg-gray-900 border-b border-gray-700">
              <tr>
                {["Email", "Role", "Active"].map((h) => (
                  <th key={h} className="py-2 px-3 text-[10px] uppercase tracking-wider text-gray-500 font-medium">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id} className="border-b border-gray-800/50">
                  <td className="py-2 px-3 text-gray-300">{u.email}</td>
                  <td className="py-2 px-3">
                    <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${
                      u.role === "admin" ? "bg-red-900/40 text-red-400" :
                      u.role === "developer" ? "bg-blue-900/40 text-blue-400" :
                      "bg-gray-800 text-gray-400"
                    }`}>
                      {u.role}
                    </span>
                  </td>
                  <td className="py-2 px-3">
                    <span className={u.is_active ? "text-green-400" : "text-gray-600"}>
                      {u.is_active ? "Yes" : "No"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {tab === "audit" && (
        <div className="overflow-auto rounded border border-gray-800">
          <table className="w-full text-left text-xs">
            <thead className="bg-gray-900 border-b border-gray-700">
              <tr>
                {["Time", "User", "Method", "Path", "Status", "IP"].map((h) => (
                  <th key={h} className="py-2 px-3 text-[10px] uppercase tracking-wider text-gray-500 font-medium">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {audit.map((a) => (
                <tr key={a.id} className="border-b border-gray-800/50">
                  <td className="py-2 px-3 text-gray-500 font-mono">{new Date(a.created_at).toLocaleTimeString()}</td>
                  <td className="py-2 px-3 text-gray-500 font-mono">{a.user_id?.slice(0, 8) ?? "—"}</td>
                  <td className="py-2 px-3 text-yellow-400 font-mono">{a.method}</td>
                  <td className="py-2 px-3 text-gray-300 font-mono">{a.path}</td>
                  <td className={`py-2 px-3 font-mono ${a.status_code < 400 ? "text-green-400" : "text-red-400"}`}>{a.status_code}</td>
                  <td className="py-2 px-3 text-gray-500">{a.ip_address ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
