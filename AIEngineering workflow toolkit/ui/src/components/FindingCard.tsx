import { ShieldAlert, Boxes, Paintbrush, Wrench, ChevronDown, ChevronRight } from 'lucide-react'
import { useState } from 'react'
import type { Finding, Severity, Domain } from '../types'

const DOMAIN_META: Record<Domain, { icon: React.ElementType; label: string; color: string }> = {
  security: { icon: ShieldAlert, label: 'Security', color: 'text-red-400' },
  architecture: { icon: Boxes, label: 'Architecture', color: 'text-blue-400' },
  style: { icon: Paintbrush, label: 'Style', color: 'text-purple-400' },
  tool: { icon: Wrench, label: 'Tool', color: 'text-gray-400' },
}

const SEV_META: Record<Severity, { label: string; dot: string; badge: string }> = {
  error: {
    label: 'ERROR',
    dot: 'bg-red-500',
    badge: 'text-red-400 bg-red-500/10 border-red-500/30',
  },
  warning: {
    label: 'WARNING',
    dot: 'bg-yellow-500',
    badge: 'text-yellow-400 bg-yellow-500/10 border-yellow-500/30',
  },
  info: {
    label: 'INFO',
    dot: 'bg-blue-500',
    badge: 'text-blue-400 bg-blue-500/10 border-blue-500/30',
  },
}

interface Props {
  finding: Finding
}

export default function FindingCard({ finding }: Props) {
  const [expanded, setExpanded] = useState(false)
  const domain = DOMAIN_META[finding.domain] ?? DOMAIN_META.tool
  const sev = SEV_META[finding.severity] ?? SEV_META.info
  const DomainIcon = domain.icon

  return (
    <div
      className="border border-gray-800 rounded-lg bg-gray-900 overflow-hidden hover:border-gray-700 transition-colors"
    >
      {/* Header row */}
      <button
        className="w-full text-left px-4 py-3 flex items-start gap-3"
        onClick={() => setExpanded((v) => !v)}
      >
        {/* Severity dot */}
        <div className={`w-2 h-2 rounded-full mt-1.5 shrink-0 ${sev.dot}`} />

        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2 mb-1">
            {/* Severity badge */}
            <span className={`text-[10px] font-bold tracking-widest px-1.5 py-0.5 rounded border ${sev.badge}`}>
              {sev.label}
            </span>

            {/* Domain chip */}
            <span className={`inline-flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider ${domain.color}`}>
              <DomainIcon size={10} />
              {domain.label}
            </span>

            {/* Rule */}
            <span className="text-[11px] font-mono text-gray-500">{finding.rule}</span>
          </div>

          {/* Message */}
          <p className="text-sm text-gray-200 leading-snug">{finding.message}</p>

          {/* File + line */}
          <p className="mt-1 text-xs font-mono text-gray-500">
            {finding.file}
            {finding.line ? `:${finding.line}` : ''}
          </p>
        </div>

        {/* Expand toggle */}
        <div className="shrink-0 text-gray-600 mt-0.5">
          {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </div>
      </button>

      {/* Expanded detail */}
      {expanded && (
        <div className="border-t border-gray-800 px-4 py-3 space-y-2.5">
          {/* Evidence */}
          <div>
            <p className="text-[10px] uppercase tracking-widest text-gray-600 mb-1">Evidence</p>
            <p className="text-xs font-mono text-gray-400 bg-gray-950 rounded px-3 py-2 border border-gray-800 leading-relaxed whitespace-pre-wrap">
              {finding.evidence}
            </p>
          </div>

          {/* Suggestion */}
          {finding.suggestion && (
            <div>
              <p className="text-[10px] uppercase tracking-widest text-gray-600 mb-1">Suggestion</p>
              <p className="text-xs text-gray-300 bg-gray-950 rounded px-3 py-2 border border-gray-800 leading-relaxed">
                → {finding.suggestion}
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
