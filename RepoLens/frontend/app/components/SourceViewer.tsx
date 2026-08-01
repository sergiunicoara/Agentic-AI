"use client";

import { useEffect, useRef, useState } from "react";
import { getFile } from "../lib/api";
import type { OpenFileRequest } from "../lib/types";

interface Props {
  repoId: string;
  request: OpenFileRequest | null;
  onClose: () => void;
}

export default function SourceViewer({ repoId, request, onClose }: Props) {
  const [content, setContent] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const highlightRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!request) return;
    setContent(null);
    setError(null);
    getFile(repoId, request.path)
      .then((file) => setContent(file.content))
      .catch((err: Error) => setError(err.message));
  }, [repoId, request?.path]);

  useEffect(() => {
    if (content !== null) {
      highlightRef.current?.scrollIntoView({ block: "center", behavior: "smooth" });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [content, request?.startLine]);

  if (!request) return null;

  const lines = content?.split("\n") ?? [];

  return (
    <div className="flex h-full flex-col border-l border-gray-800 bg-gray-950">
      <div className="flex items-center justify-between border-b border-gray-800 px-4 py-2.5">
        <span className="truncate font-mono text-xs text-gray-400">
          {request.path}:{request.startLine}-{request.endLine}
        </span>
        <button onClick={onClose} className="text-gray-500 hover:text-gray-300">
          ✕
        </button>
      </div>
      <div className="flex-1 overflow-auto">
        {error && <div className="p-4 text-sm text-red-400">{error}</div>}
        {content === null && !error && (
          <div className="p-4 text-sm text-gray-500">Loading…</div>
        )}
        {content !== null && (
          <pre className="font-mono text-xs leading-relaxed">
            {lines.map((line, i) => {
              const lineNo = i + 1;
              const highlighted = lineNo >= request.startLine && lineNo <= request.endLine;
              return (
                <div
                  key={lineNo}
                  ref={highlighted && lineNo === request.startLine ? highlightRef : undefined}
                  className={`flex px-3 ${highlighted ? "bg-emerald-950/40" : ""}`}
                >
                  <span className="mr-3 w-10 flex-shrink-0 select-none text-right text-gray-700">
                    {lineNo}
                  </span>
                  <span className="whitespace-pre text-gray-300">{line}</span>
                </div>
              );
            })}
          </pre>
        )}
      </div>
    </div>
  );
}
