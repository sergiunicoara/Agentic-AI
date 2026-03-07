import { useState } from "react";

interface Props {
  onLogin: (email: string, password: string) => Promise<void>;
}

export function LoginPage({ onLogin }: Props) {
  const [email, setEmail] = useState("admin@example.com");
  const [password, setPassword] = useState("password");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await onLogin(email, password);
    } catch {
      setError("Invalid credentials");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-950">
      <form
        onSubmit={handleSubmit}
        className="bg-gray-900 border border-gray-800 rounded-xl p-8 w-full max-w-sm"
      >
        <h1 className="text-lg font-semibold text-gray-200 mb-6">Agent Observability</h1>

        {error && (
          <p className="mb-4 text-xs text-red-400 bg-red-950/40 border border-red-800 rounded px-3 py-2">
            {error}
          </p>
        )}

        <label className="block mb-1 text-xs text-gray-500" htmlFor="email">
          Email
        </label>
        <input
          id="email"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="w-full mb-4 px-3 py-2 bg-gray-800 border border-gray-700 rounded text-sm text-gray-100 focus:outline-none focus:border-brand-500"
          required
        />

        <label className="block mb-1 text-xs text-gray-500" htmlFor="password">
          Password
        </label>
        <input
          id="password"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="w-full mb-6 px-3 py-2 bg-gray-800 border border-gray-700 rounded text-sm text-gray-100 focus:outline-none focus:border-brand-500"
          required
        />

        <button
          type="submit"
          disabled={loading}
          className="w-full py-2 bg-brand-500 hover:bg-brand-700 text-white rounded text-sm font-medium transition-colors disabled:opacity-50"
        >
          {loading ? "Signing in…" : "Sign In"}
        </button>
      </form>
    </div>
  );
}
