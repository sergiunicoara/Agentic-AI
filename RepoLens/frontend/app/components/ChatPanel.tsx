"use client";

import { useEffect, useRef, useState } from "react";
import { streamChat } from "../lib/api";
import type { ChatMessage, OpenFileRequest } from "../lib/types";
import MessageBubble from "./MessageBubble";

interface Props {
  repoId: string;
  onOpenCitation: (req: OpenFileRequest) => void;
}

export default function ChatPanel({ repoId, onOpenCitation }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [streaming, setStreaming] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    setMessages([]);
    setConversationId(null);
  }, [repoId]);

  async function sendMessage() {
    const question = input.trim();
    if (!question || streaming) return;

    setInput("");
    setMessages((prev) => [
      ...prev,
      { role: "user", content: question },
      { role: "assistant", content: "" },
    ]);
    setStreaming(true);

    try {
      for await (const event of streamChat({
        repo_id: repoId,
        conversation_id: conversationId,
        message: question,
      })) {
        if (event.type === "delta" && event.text) {
          const delta = event.text;
          setMessages((prev) => {
            const next = [...prev];
            const last = next[next.length - 1];
            next[next.length - 1] = { ...last, content: last.content + delta };
            return next;
          });
        } else if (event.type === "done") {
          if (event.conversation_id) setConversationId(event.conversation_id);
          const citations = event.citations ?? [];
          setMessages((prev) => {
            const next = [...prev];
            next[next.length - 1] = {
              ...next[next.length - 1],
              content: event.final_text ?? next[next.length - 1].content,
              citations,
            };
            return next;
          });
        } else if (event.type === "error") {
          const errorText = event.text || "Unable to complete the request.";
          setMessages((prev) => {
            const next = [...prev];
            const last = next[next.length - 1];
            next[next.length - 1] = {
              ...last,
              content: errorText,
              citations: [],
            };
            return next;
          });
        }
      }
    } catch {
      setMessages((prev) => {
        const next = [...prev];
        const last = next[next.length - 1];
        next[next.length - 1] = {
          ...last,
          content: last.content || "Unable to complete the request.",
          citations: [],
        };
        return next;
      });
    } finally {
      setStreaming(false);
    }
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 space-y-3 overflow-y-auto p-4">
        {messages.length === 0 && (
          <div className="text-sm text-gray-500">
            Ask a question about this codebase to get started.
          </div>
        )}
        {messages.map((m, i) => (
          <MessageBubble
            key={i}
            message={m}
            onOpenCitation={(path, startLine, endLine) =>
              onOpenCitation({ path, startLine, endLine })
            }
          />
        ))}
        <div ref={bottomRef} />
      </div>
      <form
        className="flex gap-2 border-t border-gray-800 p-3"
        onSubmit={(e) => {
          e.preventDefault();
          void sendMessage();
        }}
      >
        <input
          className="flex-1 rounded-md border border-gray-800 bg-gray-900 px-3 py-2 text-sm text-gray-100 placeholder:text-gray-600 focus:outline-none focus:ring-1 focus:ring-gray-700"
          placeholder="Ask about this codebase…"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={streaming}
        />
        <button
          type="submit"
          disabled={streaming || !input.trim()}
          className="rounded-md bg-gray-100 px-4 py-2 text-sm font-medium text-gray-950 disabled:opacity-40"
        >
          {streaming ? "…" : "Ask"}
        </button>
      </form>
    </div>
  );
}
