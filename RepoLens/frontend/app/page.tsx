"use client";

import { useState } from "react";
import ChatPanel from "./components/ChatPanel";
import RepoMapTree from "./components/RepoMapTree";
import RepoSelector from "./components/RepoSelector";
import SourceViewer from "./components/SourceViewer";
import type { OpenFileRequest, RepoSummary } from "./lib/types";

export default function Home() {
  const [repo, setRepo] = useState<RepoSummary | null>(null);
  const [openFile, setOpenFile] = useState<OpenFileRequest | null>(null);

  return (
    <main className="flex h-screen flex-col bg-gray-950 text-gray-100">
      <header className="flex items-center justify-between border-b border-gray-800 px-4 py-3">
        <h1 className="text-sm font-semibold tracking-tight text-gray-200">Codex</h1>
        <div className="w-96">
          <RepoSelector selectedRepoId={repo?.id ?? null} onSelect={setRepo} />
        </div>
      </header>

      {!repo ? (
        <div className="flex flex-1 items-center justify-center text-sm text-gray-500">
          Select a repo above to start.
        </div>
      ) : (
        <div className="grid flex-1 grid-cols-[240px_1fr_auto] overflow-hidden">
          <aside className="overflow-hidden border-r border-gray-800">
            <RepoMapTree
              key={repo.id}
              repoId={repo.id}
              onOpenCitation={setOpenFile}
            />
          </aside>

          <section className="overflow-hidden">
            <ChatPanel key={repo.id} repoId={repo.id} onOpenCitation={setOpenFile} />
          </section>

          {openFile && (
            <div className="w-[480px] overflow-hidden">
              <SourceViewer
                repoId={repo.id}
                request={openFile}
                onClose={() => setOpenFile(null)}
              />
            </div>
          )}
        </div>
      )}
    </main>
  );
}
