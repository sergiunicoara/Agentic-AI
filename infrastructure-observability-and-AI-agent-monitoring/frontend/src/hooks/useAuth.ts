import { useState } from "react";
import { initiateOIDCLogin, exchangeOIDCCode, logout as apiLogout } from "../api/restClient";

interface AuthState {
  token: string | null;
  role: string | null;
  email: string | null;
  department: string | null;
  clearanceLevel: number;
}

function parseSessionToken(token: string): Omit<AuthState, "token"> {
  try {
    const payload = JSON.parse(atob(token.split(".")[1]));
    return {
      role: payload.role ?? "viewer",
      email: payload.email ?? "",
      department: payload.department ?? null,
      clearanceLevel: payload.clearance_level ?? 0,
    };
  } catch {
    return { role: "viewer", email: "", department: null, clearanceLevel: 0 };
  }
}

function loadStored(): AuthState {
  const token = sessionStorage.getItem("access_token");
  if (!token) return { token: null, role: null, email: null, department: null, clearanceLevel: 0 };
  return { token, ...parseSessionToken(token) };
}

export function useAuth() {
  const [auth, setAuth] = useState<AuthState>(loadStored);

  async function loginWithOIDC() {
    await initiateOIDCLogin(); // redirects — execution stops here
  }

  async function handleOIDCCallback(code: string, state: string) {
    const token = await exchangeOIDCCode(code, state);
    setAuth({ token, ...parseSessionToken(token) });
  }

  async function logout() {
    await apiLogout();
    setAuth({ token: null, role: null, email: null, department: null, clearanceLevel: 0 });
  }

  return {
    token: auth.token,
    role: auth.role,
    email: auth.email,
    department: auth.department,
    clearanceLevel: auth.clearanceLevel,
    isAuthenticated: !!auth.token,
    loginWithOIDC,
    handleOIDCCallback,
    logout,
  };
}
