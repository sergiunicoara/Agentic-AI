"use client";

import type { ReactNode } from "react";
import type { ChatMessage } from "../lib/types";

interface Props {
  message: ChatMessage;
  onOpenCitation: (path: string, startLine: number, endLine: number) => void;
}

const CITATION_RE = /\[([^[\]:]+):(\d+)-(\d+)\]/g;

export default function MessageBubble({ message, onOpenCitation }: Props) {
  const isUser = message.role === "user";

  const parts: ReactNode[] = [];
  let lastIndex = 0;
  CITATION_RE.lastIndex = 0;
  let match: RegExpExecArray | null;
  while ((match = CITATION_RE.exec(message.content)) !== null) {
    const [full, file, start, end] = match;
    if (match.index > lastIndex) {
      parts.push(message.content.slice(lastIndex, match.index));
    }
    const startLine = parseInt(start, 10);
    const endLine = parseInt(end, 10);
    const isValidated = (message.citations ?? []).some(
      (citation) =>
        citation.file === file &&
        citation.start_line === startLine &&
        citation.end_line === endLine,
    );
    parts.push(
      isValidated ? (
        <button
          key={`${match.index}-${full}`}
          onClick={() => onOpenCitation(file, startLine, endLine)}
          className="mx-0.5 rounded bg-emerald-950 px-1.5 py-0.5 font-mono text-xs text-emerald-400 hover:bg-emerald-900"
        >
          {file}:{start}-{end}
        </button>
      ) : (
        <span key={`${match.index}-${full}`} className="font-mono text-xs text-gray-500">
          {full}
        </span>
      ),
    );
    lastIndex = match.index + full.length;
  }
  if (lastIndex < message.content.length) {
    parts.push(message.content.slice(lastIndex));
  }

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[85%] whitespace-pre-wrap rounded-lg px-4 py-2.5 text-sm leading-relaxed ${
          isUser
            ? "bg-gray-800 text-gray-100"
            : "border border-gray-800 bg-gray-900 text-gray-200"
        }`}
      >
        {parts.length > 0 ? parts : message.content || " "}
      </div>
    </div>
  );
}
