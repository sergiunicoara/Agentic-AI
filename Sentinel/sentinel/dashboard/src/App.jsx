import { useState, useRef, useCallback } from 'react'

const S = {
  root: { minHeight: '100vh', background: '#0f1117', color: '#e2e8f0', fontFamily: 'system-ui,sans-serif' },
  header: { background: '#1a1f2e', borderBottom: '1px solid #2d3748', padding: '16px 32px', display: 'flex', alignItems: 'center', gap: 12 },
  logo: { fontSize: 22, fontWeight: 700, color: '#fff', letterSpacing: -0.5 },
  subtitle: { fontSize: 13, color: '#718096' },
  body: { maxWidth: 860, margin: '0 auto', padding: '32px 24px' },
  card: { background: '#1a1f2e', border: '1px solid #2d3748', borderRadius: 10, padding: 24, marginBottom: 20 },
  label: { fontSize: 12, fontWeight: 600, color: '#718096', textTransform: 'uppercase', letterSpacing: 0.8, marginBottom: 6, display: 'block' },
  input: { width: '100%', background: '#0f1117', border: '1px solid #2d3748', borderRadius: 6, padding: '10px 12px', color: '#e2e8f0', fontSize: 14, boxSizing: 'border-box', outline: 'none' },
  row: { display: 'flex', gap: 16, alignItems: 'center', flexWrap: 'wrap', marginTop: 16 },
  check: { display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, color: '#a0aec0', cursor: 'pointer' },
  btn: { padding: '10px 24px', borderRadius: 6, fontWeight: 600, fontSize: 14, border: 'none', cursor: 'pointer', transition: 'opacity .15s' },
  btnPrimary: { background: '#4f46e5', color: '#fff' },
  btnDanger: { background: '#e53e3e', color: '#fff' },
  feed: { display: 'flex', flexDirection: 'column', gap: 8 },
  event: { borderRadius: 6, padding: '10px 14px', fontSize: 13, display: 'flex', alignItems: 'flex-start', gap: 10 },
  dot: { width: 8, height: 8, borderRadius: '50%', marginTop: 4, flexShrink: 0 },
  badge: { display: 'inline-block', padding: '2px 8px', borderRadius: 4, fontSize: 11, fontWeight: 700, letterSpacing: 0.5 },
  verdictBox: { borderRadius: 10, padding: '24px 28px', textAlign: 'center', marginBottom: 20 },
}

const STAGE_LABELS = {
  profiling: '🔍 Profiling the target, selecting which security skills apply.',
  evidence: '🛠 Four real tools running — bandit, ruff, pip-audit, semgrep. No LLM in this path.',
  auditors: '🤖 Running specialist auditors…',
  adjudicating: '⚖️ Now the trust gate.',
}

const VERDICT_STYLE = {
  fail:               { bg: '#2d1515', border: '#e53e3e', color: '#fc8181', label: '🔴 FAIL' },
  pass_with_findings: { bg: '#2d2415', border: '#d69e2e', color: '#f6e05e', label: '🟡 PASS WITH FINDINGS' },
  pass:               { bg: '#152d1e', border: '#38a169', color: '#68d391', label: '🟢 PASS' },
}

function GateBadge({ decision }) {
  const survived = decision === 'SURVIVED'
  return (
    <span style={{ ...S.badge, background: survived ? '#1a3a2a' : '#3a1a1a', color: survived ? '#68d391' : '#fc8181', border: `1px solid ${survived ? '#38a169' : '#e53e3e'}` }}>
      {survived ? '✓ SURVIVED' : '✗ DROPPED'}
    </span>
  )
}

function EventRow({ ev }) {
  if (ev.type === 'stage') {
    return (
      <div style={{ ...S.event, background: '#1a2035' }}>
        <div style={{ ...S.dot, background: '#4f46e5' }} />
        <span style={{ color: '#a5b4fc' }}>{STAGE_LABELS[ev.stage] || ev.message}</span>
      </div>
    )
  }
  if (ev.type === 'skills') {
    return (
      <div style={{ ...S.event, background: '#131820' }}>
        <div style={{ ...S.dot, background: '#718096' }} />
        <span style={{ color: '#718096' }}>Skills activated: {ev.skills.join(' · ') || 'none'}</span>
      </div>
    )
  }
  if (ev.type === 'evidence_done') {
    return (
      <div style={{ ...S.event, background: '#131820' }}>
        <div style={{ ...S.dot, background: '#4299e1' }} />
        <span style={{ color: '#90cdf4' }}>Evidence collected: <strong>{ev.count}</strong> items</span>
      </div>
    )
  }
  if (ev.type === 'auditor') {
    return (
      <div style={{ ...S.event, background: '#131820' }}>
        <div style={{ ...S.dot, background: '#805ad5' }} />
        <span style={{ color: '#d6bcfa' }}>{ev.name}: <strong>{ev.candidates}</strong> candidate{ev.candidates !== 1 ? 's' : ''}</span>
      </div>
    )
  }
  if (ev.type === 'gate_decision') {
    return (
      <div style={{ ...S.event, background: ev.decision === 'SURVIVED' ? '#111d15' : '#1d1111' }}>
        <div style={{ ...S.dot, background: ev.decision === 'SURVIVED' ? '#38a169' : '#e53e3e', marginTop: 6 }} />
        <div style={{ flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: ev.reason ? 4 : 0 }}>
            <GateBadge decision={ev.decision} />
            <span style={{ fontWeight: 600, color: '#e2e8f0' }}>{ev.title}</span>
            {ev.severity && <span style={{ ...S.badge, background: '#2d2d2d', color: '#a0aec0', border: '1px solid #4a5568', textTransform: 'uppercase' }}>{ev.severity}</span>}
          </div>
          {ev.reason && <div style={{ fontSize: 12, color: '#718096', marginTop: 2 }}>{ev.reason}</div>}
          {ev.evidence_ids && <div style={{ fontSize: 11, color: '#4a5568', marginTop: 2 }}>{ev.evidence_ids.join(', ')}</div>}
        </div>
      </div>
    )
  }
  if (ev.type === 'error') {
    return (
      <div style={{ ...S.event, background: '#2d1515' }}>
        <div style={{ ...S.dot, background: '#e53e3e' }} />
        <span style={{ color: '#fc8181' }}>Error: {ev.message}</span>
      </div>
    )
  }
  return null
}

export default function App() {
  const [target, setTarget] = useState('targets/t1_injection')
  const [redTeam, setRedTeam] = useState(false)
  const [llmAuditor, setLlmAuditor] = useState(false)
  const [scanning, setScanning] = useState(false)
  const [events, setEvents] = useState([])
  const [verdict, setVerdict] = useState(null)
  const wsRef = useRef(null)
  const feedRef = useRef(null)

  const push = useCallback((ev) => {
    setEvents(prev => [...prev, ev])
    setTimeout(() => feedRef.current?.scrollTo({ top: feedRef.current.scrollHeight, behavior: 'smooth' }), 50)
  }, [])

  const startScan = () => {
    setEvents([])
    setVerdict(null)
    setScanning(true)

    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${proto}://${location.host}/ws/scan`)
    wsRef.current = ws

    ws.onopen = () => ws.send(JSON.stringify({ target_path: target, include_red_team: redTeam, include_llm_auditor: llmAuditor }))

    ws.onmessage = ({ data }) => {
      const ev = JSON.parse(data)
      if (ev.type === 'complete') {
        setVerdict(ev)
        setScanning(false)
      }
      push(ev)
    }

    ws.onerror = () => { push({ type: 'error', message: 'WebSocket error — is the Sentinel server running?' }); setScanning(false) }
    ws.onclose = () => setScanning(false)
  }

  const stopScan = () => { wsRef.current?.close(); setScanning(false) }

  const vs = verdict ? VERDICT_STYLE[verdict.verdict] || VERDICT_STYLE.pass : null

  return (
    <div style={S.root}>
      <div style={S.header}>
        <div>
          <div style={S.logo}>🛡 Sentinel</div>
          <div style={S.subtitle}>Live Security Review Dashboard</div>
        </div>
      </div>

      <div style={S.body}>
        {vs && (
          <div style={{ ...S.verdictBox, background: vs.bg, border: `2px solid ${vs.border}` }}>
            <div style={{ fontSize: 28, fontWeight: 800, color: vs.color, marginBottom: 6 }}>{vs.label}</div>
            <div style={{ color: '#a0aec0', fontSize: 14 }}>
              {verdict.findings_count} finding{verdict.findings_count !== 1 ? 's' : ''} survived · {verdict.dropped_count} dropped by trust gate
            </div>
          </div>
        )}

        <div style={S.card}>
          <label style={S.label}>Target path</label>
          <input
            style={S.input}
            value={target}
            onChange={e => setTarget(e.target.value)}
            placeholder="targets/t1_injection"
            disabled={scanning}
          />
          <div style={S.row}>
            <label style={S.check}>
              <input type="checkbox" checked={redTeam} onChange={e => setRedTeam(e.target.checked)} disabled={scanning} />
              Red team
            </label>
            <label style={S.check}>
              <input type="checkbox" checked={llmAuditor} onChange={e => setLlmAuditor(e.target.checked)} disabled={scanning} />
              LLM auditor
            </label>
            <div style={{ flex: 1 }} />
            {scanning
              ? <button style={{ ...S.btn, ...S.btnDanger }} onClick={stopScan}>Stop</button>
              : <button style={{ ...S.btn, ...S.btnPrimary }} onClick={startScan}>Start Scan</button>
            }
          </div>
        </div>

        {events.length > 0 && (
          <div style={S.card}>
            <label style={{ ...S.label, marginBottom: 12 }}>Live event feed</label>
            <div ref={feedRef} style={{ ...S.feed, maxHeight: 480, overflowY: 'auto' }}>
              {events.map((ev, i) => <EventRow key={i} ev={ev} />)}
              {scanning && (
                <div style={{ ...S.event, background: '#131820' }}>
                  <div style={{ ...S.dot, background: '#4f46e5', animation: 'pulse 1s infinite' }} />
                  <span style={{ color: '#4f46e5' }}>Scanning…</span>
                </div>
              )}
            </div>
          </div>
        )}

        {verdict?.findings?.length > 0 && (
          <div style={S.card}>
            <label style={{ ...S.label, marginBottom: 12 }}>Surviving findings</label>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {verdict.findings.map((f, i) => (
                <div key={i} style={{ background: '#0f1117', border: '1px solid #2d3748', borderRadius: 8, padding: '12px 16px' }}>
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 6 }}>
                    <span style={{ ...S.badge, background: f.severity === 'high' || f.severity === 'critical' ? '#2d1515' : '#2d2415', color: f.severity === 'high' || f.severity === 'critical' ? '#fc8181' : '#f6e05e', border: '1px solid currentColor', textTransform: 'uppercase' }}>{f.severity}</span>
                    <span style={{ fontWeight: 600 }}>{f.title}</span>
                  </div>
                  <div style={{ fontSize: 12, color: '#718096', marginBottom: 4 }}>{f.remediation}</div>
                  <div style={{ fontSize: 11, color: '#4a5568' }}>Evidence: {f.evidence_ids.join(', ')}</div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      <style>{`@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.3} }`}</style>
    </div>
  )
}
