import type { ReviewSummary, ReviewDetail, Stats, EvalResult, ProgressEvent } from '../types'

const BASE = ''  // same origin

export async function submitReview(diff: string, title: string): Promise<{ id: string; title: string }> {
  const res = await fetch(`${BASE}/api/reviews`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ diff, title }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail ?? 'Submit failed')
  }
  return res.json()
}

export async function fetchReviews(): Promise<ReviewSummary[]> {
  const res = await fetch(`${BASE}/api/reviews`)
  if (!res.ok) throw new Error('Failed to fetch reviews')
  return res.json()
}

export async function fetchReview(id: string): Promise<ReviewDetail> {
  const res = await fetch(`${BASE}/api/reviews/${id}`)
  if (!res.ok) throw new Error('Review not found')
  return res.json()
}

export async function fetchStats(): Promise<Stats> {
  const res = await fetch(`${BASE}/api/stats`)
  if (!res.ok) throw new Error('Failed to fetch stats')
  return res.json()
}

export async function fetchEvalLatest(): Promise<EvalResult | null> {
  const res = await fetch(`${BASE}/api/eval/latest`)
  if (!res.ok) return null
  return res.json()
}

export function connectWS(
  reviewId: string,
  onEvent: (e: ProgressEvent) => void,
  onClose?: () => void,
): WebSocket {
  const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
  const host = window.location.host
  const ws = new WebSocket(`${protocol}://${host}/ws/${reviewId}`)

  ws.onmessage = (msg) => {
    try {
      const event = JSON.parse(msg.data) as ProgressEvent
      if (event.type !== 'ping') onEvent(event)
    } catch {
      /* ignore malformed */
    }
  }

  ws.onclose = () => onClose?.()
  ws.onerror = () => ws.close()

  return ws
}
