export type Severity = 'error' | 'warning' | 'info'
export type Domain = 'security' | 'architecture' | 'style' | 'tool'
export type Verdict = 'approve' | 'request_changes' | 'comment'
export type ReviewStatus = 'running' | 'complete' | 'error'
export type LayerStatus = 'idle' | 'running' | 'complete'

export interface Finding {
  id: string
  file: string
  line: number | null
  severity: Severity
  domain: Domain
  rule: string
  message: string
  evidence: string
  suggestion?: string
}

export interface ReviewDisposition {
  verdict: Verdict
  findings: Finding[]
  suppressed_count: number
  summary: string
}

export interface ReviewSummary {
  id: string
  title: string
  status: ReviewStatus
  verdict: Verdict | null
  finding_count: number
  suppressed_count: number
  created_at: string
}

export interface ReviewDetail {
  id: string
  title: string
  status: ReviewStatus
  diff: string
  result: ReviewDisposition | null
  error: string | null
  created_at: string
}

export interface Stats {
  total: number
  approve: number
  comment: number
  request_changes: number
  total_findings: number
}

export interface EvalResult {
  run_id: string
  timestamp: string
  cases_run: number
  cases_passed: number
  avg_composite: number
  passed_threshold: boolean
  threshold: number
}

// ── WebSocket progress events ──────────────────────────────────────────────────
export type ProgressEvent =
  | { type: 'layer_start'; layer: number | string; name: string; detail: string }
  | { type: 'layer_complete'; layer: number | string; name: string; detail: string }
  | { type: 'tool_result'; tool: string; tool_label: string; finding_count: number }
  | { type: 'subagent_complete'; domain: string; finding_count: number }
  | { type: 'verdict'; verdict: Verdict; finding_count: number; suppressed_count: number }
  | { type: 'complete'; review_id: string; verdict: Verdict }
  | { type: 'error'; message: string }
  | { type: 'ping' }

// ── Pipeline layer model ───────────────────────────────────────────────────────
export interface ToolResult {
  label: string
  finding_count: number
}

export interface SubagentResult {
  domain: string
  finding_count: number
}

export interface LayerState {
  status: LayerStatus
  detail: string
  toolResults: Record<string, ToolResult>   // key: tool id
  subagentResults: Record<string, SubagentResult>  // key: domain
}

export type PipelineState = Record<string, LayerState>
