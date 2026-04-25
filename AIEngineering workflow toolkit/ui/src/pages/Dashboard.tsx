import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  CheckCircle2,
  MessageSquare,
  XCircle,
  ArrowRight,
  Activity,
  FlaskConical,
  Clock,
  Zap,
} from 'lucide-react'
import { fetchReviews, fetchStats, fetchEvalLatest, fetchEvalHistory } from '../api/client'
import type { ReviewSummary, Stats, EvalResult, Verdict } from '../types'

// ── Verdict badge ──────────────────────────────────────────────────────────────

function VerdictBadge({ verdict }: { verdict: Verdict | null }) {
  if (!verdict) return <span className="text-xs text-gray-600">—</span>
  const cfg = {
    approve:         { icon: CheckCircle2, label: 'Approve',  cls: 'text-emerald-400' },
    comment:         { icon: MessageSquare, label: 'Comment', cls: 'text-blue-400' },
    request_changes: { icon: XCircle,       label: 'Changes', cls: 'text-red-400' },
  }[verdict]
  const Icon = cfg.icon
  return (
    <span className={`inline-flex items-center gap-1 text-xs font-medium ${cfg.cls}`}>
      <Icon size={12} />
      {cfg.label}
    </span>
  )
}

// ── Source badge ───────────────────────────────────────────────────────────────

function SourceBadge({ source }: { source: string }) {
  if (source !== 'hook') return null
  return (
    <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-bold bg-violet-500/15 text-violet-400 border border-violet-500/30 shrink-0">
      <Zap size={9} />
      AUTO
    </span>
  )
}

// ── Eval trend sparkline ───────────────────────────────────────────────────────

function EvalTrend({ history }: { history: EvalResult[] }) {
  if (history.length < 2) return null
  return (
    <div className="flex items-end gap-1.5 h-6">
      {history.map((run, i) => {
        const pct = (run.avg_composite / 5) * 100
        const isLast = i === history.length - 1
        return (
          <div key={run.run_id} className="flex flex-col items-center gap-0.5">
            <div
              title={`${run.run_id}: ${run.avg_composite.toFixed(2)}/5.0`}
              className={`w-2 rounded-sm transition-all ${
                run.passed_threshold ? 'bg-emerald-500' : 'bg-red-500'
              } ${isLast ? 'opacity-100' : 'opacity-50'}`}
              style={{ height: `${Math.max(4, (pct / 100) * 24)}px` }}
            />
          </div>
        )
      })}
    </div>
  )
}

// ── Time saved formatter ───────────────────────────────────────────────────────

function formatMinutes(mins: number): string {
  if (mins < 1) return '<1 min'
  if (mins < 60) return `${Math.round(mins)} min`
  const h = Math.floor(mins / 60)
  const m = Math.round(mins % 60)
  return m > 0 ? `${h}h ${m}m` : `${h}h`
}

function timeAgo(iso: string) {
  const d = Date.now() - new Date(iso).getTime()
  if (d < 60_000) return 'just now'
  if (d < 3_600_000) return `${Math.floor(d / 60_000)}m ago`
  if (d < 86_400_000) return `${Math.floor(d / 3_600_000)}h ago`
  return `${Math.floor(d / 86_400_000)}d ago`
}

// ── Dashboard ──────────────────────────────────────────────────────────────────

export default function Dashboard() {
  const [reviews, setReviews] = useState<ReviewSummary[]>([])
  const [stats, setStats] = useState<Stats | null>(null)
  const [evalResult, setEvalResult] = useState<EvalResult | null>(null)
  const [evalHistory, setEvalHistory] = useState<EvalResult[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      fetchReviews(),
      fetchStats(),
      fetchEvalLatest(),
      fetchEvalHistory(8),
    ])
      .then(([r, s, e, eh]) => {
        setReviews(r)
        setStats(s)
        setEvalResult(e)
        setEvalHistory(eh)
      })
      .finally(() => setLoading(false))
  }, [])

  const approveRate =
    stats && stats.total > 0
      ? Math.round((stats.approve / stats.total) * 100)
      : null

  const statCards = [
    {
      label: 'Total Reviews',
      value: loading ? '—' : stats?.total ?? 0,
      sub: `${stats?.approve ?? 0} approved · ${stats?.request_changes ?? 0} changes`,
      icon: Activity,
      color: 'text-gray-500',
    },
    {
      label: 'Approve Rate',
      value: loading ? '—' : (approveRate !== null ? `${approveRate}%` : '—'),
      sub: stats ? `${stats.approve} of ${stats.total} reviews` : '',
      icon: CheckCircle2,
      color: 'text-emerald-600',
    },
    {
      label: 'Findings Caught',
      value: loading ? '—' : stats?.total_findings ?? 0,
      sub: 'across all reviews',
      icon: XCircle,
      color: 'text-red-700',
    },
    {
      label: 'Est. Time Saved',
      value: loading ? '—' : formatMinutes(stats?.estimated_minutes_saved ?? 0),
      sub: 'vs 20 min manual review',
      icon: Clock,
      color: 'text-violet-600',
    },
  ]

  return (
    <div className="max-w-5xl mx-auto px-6 py-8">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-xl font-semibold text-gray-100">Dashboard</h1>
          <p className="text-sm text-gray-500 mt-0.5">Governed code review pipeline</p>
        </div>
        <Link
          to="/new"
          className="inline-flex items-center gap-2 px-4 py-2 bg-violet-600 hover:bg-violet-500 text-white text-sm font-medium rounded-lg transition-colors"
        >
          New Review <ArrowRight size={14} />
        </Link>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-4 gap-3 mb-8">
        {statCards.map(({ label, value, sub, icon: Icon, color }) => (
          <div key={label} className="bg-gray-900 border border-gray-800 rounded-xl p-4">
            <div className="flex items-center justify-between mb-3">
              <p className="text-[10px] text-gray-500 uppercase tracking-wider font-medium">
                {label}
              </p>
              <Icon size={14} className={color} />
            </div>
            <p className="text-2xl font-bold text-gray-100">{value}</p>
            <p className="text-[11px] text-gray-600 mt-1 leading-snug">{sub}</p>
          </div>
        ))}
      </div>

      {/* Eval score */}
      {evalResult && (
        <div className="mb-8 bg-gray-900 border border-gray-800 rounded-xl p-5">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-3">
              <FlaskConical size={16} className="text-violet-400" />
              <div>
                <p className="text-sm font-medium text-gray-200">Eval Regression</p>
                <p className="text-xs text-gray-500">
                  {evalResult.run_id} · {new Date(evalResult.timestamp).toLocaleDateString()}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-4">
              {/* Trend sparkline */}
              <EvalTrend history={evalHistory} />
              <div className="text-right">
                <p className="text-lg font-bold text-gray-100">
                  {evalResult.avg_composite.toFixed(1)}
                  <span className="text-sm font-normal text-gray-500">/5.0</span>
                </p>
                <p className="text-xs text-gray-500">
                  {evalResult.cases_passed}/{evalResult.cases_run} passed
                </p>
              </div>
              <span
                className={`text-xs px-2.5 py-1 rounded-full font-bold ${
                  evalResult.passed_threshold
                    ? 'bg-emerald-500/15 text-emerald-400'
                    : 'bg-red-500/15 text-red-400'
                }`}
              >
                {evalResult.passed_threshold ? 'PASS' : 'FAIL'}
              </span>
            </div>
          </div>

          {/* Score bar */}
          <div className="h-1.5 bg-gray-800 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-700 ${
                evalResult.passed_threshold ? 'bg-emerald-500' : 'bg-red-500'
              }`}
              style={{ width: `${(evalResult.avg_composite / 5) * 100}%` }}
            />
          </div>
          <div className="flex justify-between mt-1.5">
            <span className="text-[10px] text-gray-700">0</span>
            <span className="text-[10px] text-gray-700">
              threshold {evalResult.threshold} · run{' '}
              <code className="font-mono">python main.py eval --compare</code> to track drift
            </span>
            <span className="text-[10px] text-gray-700">5</span>
          </div>
        </div>
      )}

      {/* Recent reviews */}
      <div>
        <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">
          Recent Reviews
        </h2>

        {loading ? (
          <div className="space-y-2">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-14 bg-gray-900 rounded-lg animate-pulse" />
            ))}
          </div>
        ) : reviews.length === 0 ? (
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-10 text-center">
            <p className="text-gray-500 text-sm">No reviews yet.</p>
            <Link
              to="/new"
              className="mt-3 inline-flex items-center gap-1.5 text-violet-400 text-sm hover:text-violet-300 transition-colors"
            >
              Submit your first diff <ArrowRight size={13} />
            </Link>
          </div>
        ) : (
          <div className="space-y-1.5">
            {reviews.map((review) => (
              <Link
                key={review.id}
                to={`/reviews/${review.id}`}
                className="flex items-center gap-3 bg-gray-900 border border-gray-800 rounded-lg px-4 py-3 hover:border-gray-700 hover:bg-gray-900/80 transition-all group"
              >
                {/* Status dot */}
                <div
                  className={`w-2 h-2 rounded-full shrink-0 ${
                    review.status === 'running'
                      ? 'bg-violet-500 animate-pulse'
                      : review.status === 'error'
                      ? 'bg-red-500'
                      : 'bg-gray-700'
                  }`}
                />

                {/* Source badge */}
                <SourceBadge source={review.source} />

                {/* Title */}
                <p className="flex-1 text-sm text-gray-300 group-hover:text-gray-100 truncate transition-colors">
                  {review.title}
                </p>

                {/* Verdict */}
                <VerdictBadge verdict={review.verdict} />

                {/* Finding count */}
                <span className="text-xs text-gray-600 w-20 text-right shrink-0">
                  {review.finding_count > 0
                    ? `${review.finding_count} finding${review.finding_count !== 1 ? 's' : ''}`
                    : ''}
                </span>

                {/* Elapsed */}
                {review.elapsed_ms > 0 && (
                  <span className="text-xs text-gray-700 w-12 text-right shrink-0 font-mono">
                    {(review.elapsed_ms / 1000).toFixed(0)}s
                  </span>
                )}

                {/* Time */}
                <span className="text-xs text-gray-600 w-16 text-right shrink-0">
                  {timeAgo(review.created_at)}
                </span>

                <ArrowRight
                  size={13}
                  className="text-gray-700 group-hover:text-gray-500 transition-colors shrink-0"
                />
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
