import { useEffect, useRef } from "react";
import { subscribeEvents } from "../api/grpcClient";
import { useTraceStore } from "../store/traceStore";

interface Options {
  filterAgents?: string[];
  filterTraceId?: string;
}

export function useEventStream(token: string | null, opts?: Options) {
  const addEvent = useTraceStore((s) => s.addEvent);
  const cancelRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    if (!token) return;

    const cancel = subscribeEvents({
      sessionToken: token,
      filterAgents: opts?.filterAgents,
      filterTraceId: opts?.filterTraceId,
      onEvent: addEvent,
      onError: (err) => console.error("[stream error]", err),
    });

    cancelRef.current = cancel;
    return () => {
      cancel();
      cancelRef.current = null;
    };
  }, [token, opts?.filterAgents?.join(","), opts?.filterTraceId]);
}
