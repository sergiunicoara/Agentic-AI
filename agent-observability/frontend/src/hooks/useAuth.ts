import { useState } from "react";
import { login as apiLogin, logout as apiLogout } from "../api/restClient";

interface AuthState {
  token: string | null;
  role: string | null;
  email: string | null;
}

function parseToken(token: string): { role: string; email: string } {
  try {
    const payload = JSON.parse(atob(token.split(".")[1]));
    return { role: payload.role ?? "viewer", email: payload.email ?? "" };
  } catch {
    return { role: "viewer", email: "" };
  }
}

export function useAuth() {
  const stored = localStorage.getItem("access_token");
  const parsed = stored ? parseToken(stored) : null;

  const [auth, setAuth] = useState<AuthState>({
    token: stored,
    role: parsed?.role ?? null,
    email: parsed?.email ?? null,
  });

  async function login(email: string, password: string) {
    const token = await apiLogin(email, password);
    const { role } = parseToken(token);
    setAuth({ token, role, email });
  }

  async function logout() {
    await apiLogout();
    setAuth({ token: null, role: null, email: null });
  }

  return {
    token: auth.token,
    role: auth.role,
    email: auth.email,
    isAuthenticated: !!auth.token,
    login,
    logout,
  };
}
