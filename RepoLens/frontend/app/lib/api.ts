import type { ChatEvent, ChatRequest, FileContent, RepoSummary, TreeNode } from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function listRepos(): Promise<RepoSummary[]> {
  const res = await fetch(`${API_URL}/repos`);
  if (!res.ok) throw new Error(`Failed to load repos (${res.status})`);
  return res.json();
}

export async function getRepoMap(repoId: string): Promise<TreeNode[]> {
  const res = await fetch(`${API_URL}/repo-map?repo_id=${encodeURIComponent(repoId)}`);
  if (!res.ok) throw new Error(`Failed to load repo map (${res.status})`);
  return res.json();
}

export async function getFile(repoId: string, path: string): Promise<FileContent> {
  const params = new URLSearchParams({ repo_id: repoId, path });
  const res = await fetch(`${API_URL}/file?${params.toString()}`);
  if (!res.ok) throw new Error(`Failed to load file (${res.status})`);
  return res.json();
}

/**
 * /chat is a POST endpoint streaming Server-Sent Events — the browser's EventSource
 * only supports GET, so we parse the `data: {...}\n\n` framing manually off the
 * fetch() response body stream instead.
 */
export async function* streamChat(request: ChatRequest): AsyncGenerator<ChatEvent> {
  const res = await fetch(`${API_URL}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!res.ok || !res.body) {
    throw new Error(`Chat request failed (${res.status})`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let sepIndex: number;
    while ((sepIndex = buffer.indexOf("\n\n")) !== -1) {
      const rawEvent = buffer.slice(0, sepIndex);
      buffer = buffer.slice(sepIndex + 2);
      const dataLine = rawEvent.split("\n").find((line) => line.startsWith("data: "));
      if (!dataLine) continue;
      yield JSON.parse(dataLine.slice("data: ".length)) as ChatEvent;
    }
  }
}
