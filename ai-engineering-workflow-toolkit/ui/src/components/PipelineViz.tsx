import { CheckCircle2, Circle, Loader2, AlertCircle } from 'lucide-react'
import type { PipelineState, LayerStatus } from '../types'

const LAYERS = [
  {
    id: '1',
    label: 'Layer 1',
    name: 'Skills',
    description: 'Versioned skill library',
  },
  {
    id: '2',
    label: 'Layer 2',
    name: 'Orchestrator',
    description: 'Routing & coordination',
  },
  {
    id: '3a',
    label: 'Layer 3a',
    name: 'MCP Tools',
    description: 'ruff · mypy · bandit',
    tools: [
      { key: 'linter', label: 'ruff' },
      { key: 'type_checker', label: 'mypy' },
      { key: 'security_scanner', label: 'bandit' },
    ],
  },
  {
    id: '3b',
    label: 'Layer 3b',
    name: 'Subagents',
    description: 'Parallel specialised reviewers',
    subagents: ['security', 'architecture', 'style'],
  },
  {
    id: '4',
    label: 'Layer 4',
    name: 'Review Agent',
    description: 'Traceability validation',
  },
]

function StatusIcon({ status }: { status: LayerStatus }) {
  if (status === 'complete')
    return <CheckCircle2 size={16} className="text-emerald-400 shrink-0" />
  if (status === 'running')
    return <Loader2 size={16} className="text-violet-400 shrink-0 animate-spin" />
  return <Circle size={16} className="text-gray-700 shrink-0" />
}

function statusRing(status: LayerStatus) {
  if (status === 'complete') return 'border-emerald-500/40 bg-emerald-500/5'
  if (status === 'running') return 'border-violet-500/50 bg-violet-500/5'
  return 'border-gray-800 bg-gray-900'
}

function ToolBadge({
  label,
  count,
  running,
}: {
  label: string
  count?: number
  running: boolean
}) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-xs border ${
        count !== undefined
          ? 'border-gray-700 bg-gray-800 text-gray-300'
          : running
          ? 'border-violet-800 bg-violet-900/30 text-violet-400'
          : 'border-gray-800 bg-gray-900 text-gray-600'
      }`}
    >
      {running && count === undefined && (
        <Loader2 size={10} className="animate-spin text-violet-400" />
      )}
      <span className="font-mono">{label}</span>
      {count !== undefined && (
        <span className={count > 0 ? 'text-amber-400' : 'text-gray-500'}>
          {count} {count === 1 ? 'finding' : 'findings'}
        </span>
      )}
    </span>
  )
}

function SubagentBadge({
  domain,
  count,
  running,
}: {
  domain: string
  count?: number
  running: boolean
}) {
  const colors: Record<string, string> = {
    security: 'text-red-300 border-red-800 bg-red-900/20',
    architecture: 'text-blue-300 border-blue-800 bg-blue-900/20',
    style: 'text-purple-300 border-purple-800 bg-purple-900/20',
  }
  const idle = 'text-gray-600 border-gray-800 bg-gray-900'

  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-xs border ${
        count !== undefined || running ? colors[domain] ?? idle : idle
      }`}
    >
      {running && count === undefined && (
        <Loader2 size={10} className="animate-spin" />
      )}
      <span className="capitalize font-medium">{domain}</span>
      {count !== undefined && (
        <span className="opacity-70">
          {count} {count === 1 ? 'finding' : 'findings'}
        </span>
      )}
    </span>
  )
}

interface Props {
  state: PipelineState
  hasError?: boolean
}

export default function PipelineViz({ state, hasError }: Props) {
  return (
    <div className="space-y-0">
      {LAYERS.map((layer, idx) => {
        const ls = state[layer.id] ?? { status: 'idle', detail: '', toolResults: {}, subagentResults: {} }
        const isLast = idx === LAYERS.length - 1

        return (
          <div key={layer.id} className="flex gap-0">
            {/* Connector column */}
            <div className="flex flex-col items-center w-8 shrink-0">
              <div className={`w-px flex-1 ${idx === 0 ? 'opacity-0' : 'bg-gray-800'}`} />
              <div
                className={`w-2 h-2 rounded-full shrink-0 my-0.5 ${
                  ls.status === 'complete'
                    ? 'bg-emerald-500'
                    : ls.status === 'running'
                    ? 'bg-violet-500 animate-pulse'
                    : 'bg-gray-700'
                }`}
              />
              <div className={`w-px flex-1 ${isLast ? 'opacity-0' : 'bg-gray-800'}`} />
            </div>

            {/* Card */}
            <div className={`flex-1 mb-2 mt-0 border rounded-lg px-4 py-3 transition-all duration-300 ${statusRing(ls.status)}`}>
              <div className="flex items-start gap-3">
                <StatusIcon status={hasError ? 'idle' : ls.status} />
                <div className="flex-1 min-w-0">
                  <div className="flex items-baseline gap-2 flex-wrap">
                    <span className="text-[10px] font-mono text-gray-600 uppercase tracking-widest">
                      {layer.label}
                    </span>
                    <span className="text-sm font-semibold text-gray-200">{layer.name}</span>
                    <span className="text-xs text-gray-600">{layer.description}</span>
                  </div>

                  {ls.detail && (
                    <p className="mt-1 text-xs text-gray-400 leading-relaxed">{ls.detail}</p>
                  )}

                  {/* MCP Tool badges */}
                  {layer.tools && ls.status !== 'idle' && (
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {layer.tools.map(({ key, label }) => {
                        const tr = ls.toolResults[key]
                        return (
                          <ToolBadge
                            key={key}
                            label={label}
                            count={tr?.finding_count}
                            running={ls.status === 'running'}
                          />
                        )
                      })}
                    </div>
                  )}

                  {/* Subagent badges */}
                  {layer.subagents && ls.status !== 'idle' && (
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {layer.subagents.map((domain) => {
                        const sr = ls.subagentResults[domain]
                        return (
                          <SubagentBadge
                            key={domain}
                            domain={domain}
                            count={sr?.finding_count}
                            running={ls.status === 'running'}
                          />
                        )
                      })}
                    </div>
                  )}
                </div>

                {/* Status pill */}
                {ls.status !== 'idle' && (
                  <span
                    className={`shrink-0 text-[10px] uppercase tracking-widest font-semibold px-2 py-0.5 rounded ${
                      ls.status === 'complete'
                        ? 'text-emerald-400 bg-emerald-500/10'
                        : 'text-violet-400 bg-violet-500/10'
                    }`}
                  >
                    {ls.status === 'complete' ? 'Done' : 'Running'}
                  </span>
                )}
              </div>
            </div>
          </div>
        )
      })}

      {hasError && (
        <div className="flex items-center gap-2 text-red-400 text-sm px-8 pt-1">
          <AlertCircle size={14} />
          Pipeline encountered an error
        </div>
      )}
    </div>
  )
}
