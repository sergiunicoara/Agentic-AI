import { useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";

interface Props {
  onCallback: (code: string, state: string) => Promise<void>;
}

export function OIDCCallbackPage({ onCallback }: Props) {
  const navigate = useNavigate();
  const called = useRef(false);

  useEffect(() => {
    if (called.current) return;
    called.current = true;

    const params = new URLSearchParams(window.location.search);
    const code  = params.get("code")  ?? "";
    const state = params.get("state") ?? "";

    if (!code || !state) {
      navigate("/", { replace: true });
      return;
    }

    onCallback(code, state)
      .then(() => navigate("/", { replace: true }))
      .catch(() => navigate("/", { replace: true }));
  }, []);

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-950">
      <p className="text-sm text-gray-400">Completing sign-in…</p>
    </div>
  );
}
