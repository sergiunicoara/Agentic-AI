import { useState } from "react";

interface Props {
  onLogin: () => Promise<void>;
}

export function LoginPage({ onLogin }: Props) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function handleLogin() {
    setError("");
    setLoading(true);
    try {
      await onLogin(); // triggers OIDC redirect — page navigates away
    } catch {
      setError("Failed to initiate login. Check OIDC configuration.");
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-950">
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-8 w-full max-w-sm">
        <h1 className="text-lg font-semibold text-gray-200 mb-2">Agent Observability</h1>
        <p className="text-xs text-gray-500 mb-6">Sign in with your organisation account</p>

        {error && (
          <p className="mb-4 text-xs text-red-400 bg-red-950/40 border border-red-800 rounded px-3 py-2">
            {error}
          </p>
        )}

        <button
          onClick={handleLogin}
          disabled={loading}
          className="w-full py-2 bg-brand-500 hover:bg-brand-700 text-white rounded text-sm font-medium transition-colors disabled:opacity-50"
        >
          {loading ? "Redirecting…" : "Sign in with OIDC"}
        </button>
      </div>
    </div>
  );
}
