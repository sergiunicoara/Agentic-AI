export interface Citation {
  file: string;
  start_line: number;
  end_line: number;
}

export interface ChatEvent {
  type: "delta" | "done" | "error";
  text?: string | null;
  final_text?: string | null;
  citations?: Citation[] | null;
  conversation_id?: string | null;
}

export interface ChatRequest {
  repo_id: string;
  conversation_id?: string | null;
  message: string;
}

export interface RepoSummary {
  id: string;
  source_url: string;
  file_count: number;
  chunk_count: number;
  indexed_at: string | null;
}

export interface SymbolNode {
  symbol_path: string;
  kind: string;
  start_line: number;
  end_line: number;
  children: SymbolNode[];
}

export interface TreeNode {
  type: "dir" | "file";
  name: string;
  path: string | null;
  symbols: SymbolNode[];
  children: TreeNode[];
}

export interface FileContent {
  path: string;
  content: string;
  language: string | null;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
}

export interface OpenFileRequest {
  path: string;
  startLine: number;
  endLine: number;
}
