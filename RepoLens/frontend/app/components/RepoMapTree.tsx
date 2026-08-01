"use client";

import { useEffect, useState } from "react";
import { getRepoMap } from "../lib/api";
import type { OpenFileRequest, SymbolNode, TreeNode } from "../lib/types";

interface Props {
  repoId: string;
  onOpenCitation: (req: OpenFileRequest) => void;
}

export default function RepoMapTree({ repoId, onOpenCitation }: Props) {
  const [tree, setTree] = useState<TreeNode[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    getRepoMap(repoId)
      .then(setTree)
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [repoId]);

  if (loading) return <div className="p-3 text-sm text-gray-500">Loading repo map…</div>;
  if (error) return <div className="p-3 text-sm text-red-400">{error}</div>;

  return (
    <div className="overflow-y-auto p-2 text-sm">
      {tree.map((node) => (
        <TreeNodeView
          key={node.path ?? node.name}
          node={node}
          depth={0}
          onOpenCitation={onOpenCitation}
        />
      ))}
    </div>
  );
}

function TreeNodeView({
  node,
  depth,
  onOpenCitation,
}: {
  node: TreeNode;
  depth: number;
  onOpenCitation: (req: OpenFileRequest) => void;
}) {
  const [open, setOpen] = useState(depth < 1);

  if (node.type === "dir") {
    return (
      <div>
        <button
          className="flex w-full items-center gap-1 rounded px-1.5 py-1 text-left text-gray-300 hover:bg-gray-900"
          style={{ paddingLeft: `${depth * 12 + 6}px` }}
          onClick={() => setOpen((o) => !o)}
        >
          <span className="text-gray-600">{open ? "▾" : "▸"}</span>
          <span>{node.name}/</span>
        </button>
        {open &&
          node.children.map((child) => (
            <TreeNodeView
              key={child.path ?? child.name}
              node={child}
              depth={depth + 1}
              onOpenCitation={onOpenCitation}
            />
          ))}
      </div>
    );
  }

  return (
    <div>
      <button
        className="flex w-full items-center gap-1 rounded px-1.5 py-1 text-left text-gray-400 hover:bg-gray-900"
        style={{ paddingLeft: `${depth * 12 + 6}px` }}
        onClick={() => setOpen((o) => !o)}
      >
        <span className="text-gray-700">
          {node.symbols.length > 0 ? (open ? "▾" : "▸") : " "}
        </span>
        <span className="truncate">{node.name}</span>
      </button>
      {open &&
        node.symbols.map((symbol) => (
          <SymbolView
            key={symbol.symbol_path}
            symbol={symbol}
            depth={depth + 1}
            path={node.path ?? ""}
            onOpenCitation={onOpenCitation}
          />
        ))}
    </div>
  );
}

const KIND_LABEL: Record<string, string> = {
  function: "fn",
  class: "cls",
  method: "m",
  markdown_section: "§",
};

function SymbolView({
  symbol,
  depth,
  path,
  onOpenCitation,
}: {
  symbol: SymbolNode;
  depth: number;
  path: string;
  onOpenCitation: (req: OpenFileRequest) => void;
}) {
  return (
    <div>
      <button
        className="flex w-full items-center gap-1.5 rounded px-1.5 py-0.5 text-left text-xs text-gray-500 hover:bg-gray-900 hover:text-gray-300"
        style={{ paddingLeft: `${depth * 12 + 6}px` }}
        onClick={() =>
          onOpenCitation({ path, startLine: symbol.start_line, endLine: symbol.end_line })
        }
      >
        <span className="rounded bg-gray-900 px-1 font-mono text-[10px] uppercase text-gray-600">
          {KIND_LABEL[symbol.kind] ?? symbol.kind.slice(0, 2)}
        </span>
        <span className="truncate">{symbol.symbol_path.split(".").pop()}</span>
      </button>
      {symbol.children.map((child) => (
        <SymbolView
          key={child.symbol_path}
          symbol={child}
          depth={depth + 1}
          path={path}
          onOpenCitation={onOpenCitation}
        />
      ))}
    </div>
  );
}
