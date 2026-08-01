"use client";

import { useEffect, useState } from "react";
import { listRepos } from "../lib/api";
import type { RepoSummary } from "../lib/types";

interface Props {
  selectedRepoId: string | null;
  onSelect: (repo: RepoSummary) => void;
}

export default function RepoSelector({ selectedRepoId, onSelect }: Props) {
  const [repos, setRepos] = useState<RepoSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listRepos()
      .then((result) => {
        setRepos(result);
        if (result.length > 0 && !selectedRepoId) {
          const demoRepo = result.find(
            (repo) => repo.source_url === "https://github.com/fastapi/fastapi.git",
          );
          onSelect(demoRepo ?? result[0]);
        }
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (loading) return <div className="text-sm text-gray-500">Loading repos…</div>;
  if (error) return <div className="text-sm text-red-400">{error}</div>;
  if (repos.length === 0) {
    return (
      <div className="text-sm text-gray-500">
        No repos indexed yet. Run{" "}
        <code className="rounded bg-gray-900 px-1 py-0.5 text-gray-300">
          python -m app.ingest &lt;url&gt;
        </code>
        .
      </div>
    );
  }

  return (
    <select
      className="w-full rounded-md border border-gray-800 bg-gray-900 px-3 py-2 text-sm text-gray-100 focus:outline-none focus:ring-1 focus:ring-gray-700"
      value={selectedRepoId ?? ""}
      onChange={(e) => {
        const repo = repos.find((r) => r.id === e.target.value);
        if (repo) onSelect(repo);
      }}
    >
      {repos.map((repo) => (
        <option key={repo.id} value={repo.id}>
          {repo.source_url} ({repo.file_count} files, {repo.chunk_count} chunks)
        </option>
      ))}
    </select>
  );
}
