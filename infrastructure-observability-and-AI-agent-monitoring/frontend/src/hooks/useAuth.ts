import { useEffect, useState } from "react";
import {
  initiateOIDCLogin,
  exchangeOIDCCode,
  logout as apiLogout,
  SESSION_EXPIRED_EVENT,
} from "../api/restClient";

interface AuthState {
  token: string | null;
  role: string | null;
  email: string | null;
  department: string | null;
  clearanceLevel: number;
}

const LOGGED_OUT: AuthState = {
  token: null,
  role: null,
  email: null,
  department: null,
  clearanceLevel: 0,
};

/**
 * JWT payloads are base64url with the padding stripped, which `atob` rejects:
 * any token containing `-` or `_` threw here and silently downgraded the user
 * to "viewer", hiding admin navigation from actual admins.
 */
function decodeJwtPayload(token: string): Record<string, any> {
  const segment = token.split(".")[1] ?? "";
  const base64 = segment.replace(/-/g, "+").replace(/_/g, "/");
  const padded = base64 + "=".repeat((4 - (base64.length % 4)) % 4);
  const binary = atob(padded);
  const utf8 = decodeURIComponent(
    Array.from(binary, (c) => "%" + c.charCodeAt(0).toString(16).padStart(2, "0")).join("")
  );
  return JSON.parse(utf8);
}

function parseSessionToken(token: string): Omit<AuthState, "token"> {
  try {
    const payload = decodeJwtPayload(token);
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
  if (!token) return LOGGED_OUT;
  return { token, ...parseSessionToken(token) };
}

export function useAuth() {
  const [auth, setAuth] = useState<AuthState>(loadStored);

  // The token can be revoked or expire while the tab is open; restClient
  // reports that here so the app falls back to the login screen.
  useEffect(() => {
    const onExpired = () => setAuth(LOGGED_OUT);
    window.addEventListener(SESSION_EXPIRED_EVENT, onExpired);
    return () => window.removeEventListener(SESSION_EXPIRED_EVENT, onExpired);
  }, []);

  async function loginWithOIDC() {
    await initiateOIDCLogin(); // redirects - execution stops here
  }

  async function handleOIDCCallback(code: string, state: string) {
    const token = await exchangeOIDCCode(code, state);
    setAuth({ token, ...parseSessionToken(token) });
  }

  async function logout() {
    await apiLogout();
    setAuth(LOGGED_OUT);
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
