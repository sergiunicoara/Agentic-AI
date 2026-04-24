import { useEffect, useReducer, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import {
  CheckCircle2,
  MessageSquare,
  XCircle,
  ArrowLeft,
  ShieldAlert,
  Boxes,
  Paintbrush,
  Layers,
  EyeOff,
} from 'lucide-react'
import { fetchReview, connectWS } from '../api/client'
import PipelineViz from '../components/PipelineViz'
import FindingCard from '../components/FindingCard'
import type {
  ReviewDetail as ReviewDetailType,
  PipelineState,
  LayerState,
  ProgressEvent,
  Verdict,
  Domain,
} from '../types'

// ── Pipeline state reducer ────────────────────────────────────────────────────

const INITIAL_LAYER = (): LayerState => ({
  status: 'idle',
  detail: '',
  toolResults: {},
  subagentResults: {},
})

const INITIAL_STATE: PipelineState = {
  '1': INITIAL_LAYER(),
  '2': INITIAL_LAYER(),
  '3a': INITIAL_LAYER(),
  '3b': INITIAL_LAYER(),
  '4': INITIAL_LAYER(),
}

function pipelineReducer(
  state: PipelineState,
  event: ProgressEvent,
): PipelineState {
  if (event.type === 'layer_start') {
    const id = String(event.layer)
    return {
      ...state,
      [id]: { ...INITIAL_LAYER(), status: 'running', detail: event.detail },
    }
  }

  if (event.type === 'layer_complete') {
    const id = String(event.layer)
    return {
      ...state,
      [id]: { ...(state[id] ?? INITIAL_LAYER()), status: 'complete', detail: event.detail },
    }
  }

  if (event.type === 'tool_result') {
    return {
      ...state,
      '3a': {
        ...(state['3a'] ?? INITIAL_LAYER()),
        toolResults: {
          ...state['3a']?.toolResults,
          [event.tool]: { label: event.tool_label, finding_count: event.finding_count },
        },
      },
    }
  }

  if (event.type === 'subagent_complete') {
    return {
      ...state,
      '3b': {
        ...(state['3b'] ?? INITIAL_LAYER()),
        subagentResults: {
          ...state['3b']?.subagentResults,
          [event.domain]: { domain: event.domain, finding_count: event.finding_count },
        },
      },
    }
  }

  return state
}

// ── Verdict banner ────────────────────────────────────────────────────────────

const VERDICT_CFG = {
  approve: {
    icon: CheckCircle2,
    label: 'Approved',
    sub: 'No blocking issues. Safe to merge.',
    border: 'border-emerald-500/30',
    bg: 'bg-emerald-500/5',
    text: 'text-emerald-400',
    bar: 'bg-emerald-500',
  },
  comment: {
    icon: MessageSquare,
    label: 'Comment',
    sub: 'Informational findings only. No blocking issues.',
    border: 'border-blue-500/30',
    bg: 'bg-blue-500/5',
    text: 'text-blue-400',
    bar: 'bg-blue-500',
  },
  request_changes: {
    icon: XCircle,
    label: 'Request Changes',
    sub: 'One or more error-severity findings require resolution.',
    border: 'border-red-500/30',
    bg: 'bg-red-500/5',
    text: 'text-red-400',
    bar: 'bg-red-500',
  },
}

function VerdictBanner({
  verdict,
  findingCount,
  suppressedCount,
  summary,
}: {
  verdict: Verdict
  findingCount: number
  suppressedCount: number
  summary: string
}) {
  const cfg = VERDICT_CFG[verdict]
  const Icon = cfg.icon

  return (
    <div className={`border rounded-xl p-5 ${cfg.border} ${cfg.bg} mb-6`}>
      <div className="flex items-start gap-4">
        <Icon size={22} className={cfg.text} />
        <div className="flex-1 min-w-0">
          <div className="flex items-baseline gap-3 flex-wrap">
            <h2 className={`text-lg font-bold ${cfg.text}`}>{cfg.label}</h2>
            <p className="text-sm text-gray-400">{cfg.sub}</p>
          </div>
          {summary && (
            <p className="mt-2 text-sm text-gray-400 leading-relaxed">{summary}</p>
          )}
          <div className="mt-3 flex flex-wrap gap-4 text-xs text-gray-500">
            <span>{findingCount} finding{findingCount !== 1 ? 's' : ''}</span>
            {suppressedCount > 0 && (
              <span className="flex items-center gap-1">
                <EyeOff size={11} />
                {suppressedCount} suppressed (no traceable evidence)
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Domain filter ─────────────────────────────────────────────────────────────

const DOMAIN_TABS: { key: Domain | 'all'; icon: React.ElementType; label: string }[] = [
  { key: 'all', icon: Layers, label: 'All' },
  { key: 'security', icon: ShieldAlert, label: 'Security' },
  { key: 'architecture', icon: Boxes, label: 'Architecture' },
  { key: 'style', icon: Paintbrush, label: 'Style' },
]

// ── Main component ────────────────────────────────────────────────────────────

export default function ReviewDetail() {
  const { id } = useParams<{ id: string }>()
  const [review, setReview] = useState<ReviewDetailType | null>(null)
  const [pipelineState, dispatch] = useReducer(pipelineReducer, INITIAL_STATE)
  const [done, setDone] = useState(false)
  const [hasError, setHasError] = useState(false)
  const [domainFilter, setDomainFilter] = useState<Domain | 'all'>('all')

  // Load review + connect WebSocket
  useEffect(() => {
    if (!id) return

    fetchReview(id).then((r) => {
      setReview(r)
      if (r.status === 'complete' || r.status === 'error') {
        setDone(true)
        if (r.status === 'error') setHasError(true)
      }
    })

    const ws = connectWS(
      id,
      (event: ProgressEvent) => {
        dispatch(event)
        if (event.type === 'complete') {
          setDone(true)
          // Reload from server to get full disposition
          fetchReview(id).then(setReview)
        }
        if (event.type === 'error') {
          setDone(true)
          setHasError(true)
          fetchReview(id).then(setReview)
        }
      },
      () => {
        // WS closed — if not done, reload review
        fetchReview(id).then((r) => {
          setReview(r)
          if (r.status !== 'running') setDone(true)
        })
      },
    )

    return () => ws.close()
  }, [id])

  const disposition = review?.result
  const findings = disposition?.findings ?? []
  const filtered =
    domainFilter === 'all' ? findings : findings.filter((f) => f.domain === domainFilter)

  const domainCounts = findings.reduce<Record<string, number>>((acc, f) => {
    acc[f.domain] = (acc[f.domain] ?? 0) + 1
    return acc
  }, {})

  return (
    <div className="max-w-4xl mx-auto px-6 py-8">
      {/* Back */}
      <Link
        to="/"
        className="inline-flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-300 transition-colors mb-6"
      >
        <ArrowLeft size={14} />
        Dashboard
      </Link>

      {/* Title */}
      <div className="mb-8">
        <h1 className="text-xl font-semibold text-gray-100">
          {review?.title ?? 'Loading…'}
        </h1>
        {review && (
          <p className="text-xs text-gray-600 mt-1 font-mono">
            {review.id}
            {review.created_at &&
              ` · ${new Date(review.created_at).toLocaleString()}`}
          </p>
        )}
      </div>

      {/* Pipeline visualization */}
      <div className="mb-8">
        <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-4">
          Pipeline Progress
        </h2>
        <PipelineViz state={pipelineState} hasError={hasError} />
      </div>

      {/* Results — show once done */}
      {done && disposition && (
        <>
          {/* Verdict */}
          <VerdictBanner
            verdict={disposition.verdict}
            findingCount={findings.length}
            suppressedCount={disposition.suppressed_count}
            summary={disposition.summary}
          />

          {/* Findings */}
          {findings.length > 0 && (
            <div>
              {/* Domain filter tabs */}
              <div className="flex items-center gap-1 mb-4 flex-wrap">
                {DOMAIN_TABS.map(({ key, icon: Icon, label }) => {
                  const count = key === 'all' ? findings.length : (domainCounts[key] ?? 0)
                  const active = domainFilter === key
                  return (
                    <button
                      key={key}
                      onClick={() => setDomainFilter(key as Domain | 'all')}
                      className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                        active
                          ? 'bg-violet-600/20 text-violet-300 border border-violet-600/40'
                          : 'text-gray-500 hover:text-gray-300 border border-transparent hover:bg-gray-800'
                      }`}
                    >
                      <Icon size={11} />
                      {label}
                      {count > 0 && (
                        <span
                          className={`text-[10px] px-1.5 py-0.5 rounded-full ${
                            active ? 'bg-violet-600/30 text-violet-300' : 'bg-gray-800 text-gray-500'
                          }`}
                        >
                          {count}
                        </span>
                      )}
                    </button>
                  )
                })}
              </div>

              {/* Finding list */}
              <div className="space-y-2">
                {filtered.map((finding) => (
                  <FindingCard key={finding.id} finding={finding} />
                ))}
                {filtered.length === 0 && (
                  <p className="text-sm text-gray-600 py-4 text-center">
                    No {domainFilter} findings.
                  </p>
                )}
              </div>
            </div>
          )}

          {findings.length === 0 && disposition.verdict === 'approve' && (
            <div className="text-center py-8 text-gray-600 text-sm">
              No findings — this diff is clean.
            </div>
          )}
        </>
      )}

      {/* Running state with no results yet */}
      {!done && (
        <div className="text-center py-6 text-gray-600 text-sm">
          <div className="inline-flex items-center gap-2">
            <span className="w-3.5 h-3.5 border border-gray-700 border-t-violet-500 rounded-full animate-spin" />
            Pipeline running…
          </div>
        </div>
      )}

      {/* Error state */}
      {done && hasError && review?.error && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-5 text-sm text-red-400">
          <p className="font-semibold mb-1">Pipeline error</p>
          <p className="font-mono text-xs text-red-400/70">{review.error}</p>
        </div>
      )}
    </div>
  )
}
