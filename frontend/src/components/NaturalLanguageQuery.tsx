'use client'
/**
 * NaturalLanguageQuery — UrbanEye AI
 * =====================================
 * Ask a plain-English question about vehicle/traffic data.
 * Calls POST /query on the backend and renders the structured result.
 */

import { useState, useRef, useCallback, useEffect } from 'react'
import { Search, Sparkles, ChevronRight, AlertCircle, Loader2, RotateCcw } from 'lucide-react'

// ── types (mirrors backend NLQueryResponse) ───────────────────────────────────
interface NLQueryResponse {
  question       : string
  interpreted_as : string
  intent         : string
  answer_text    : string
  columns        : string[]
  rows           : Record<string, string | number>[]
  total_results  : number
  parameters     : Record<string, unknown>
  confidence     : 'HIGH' | 'MEDIUM' | 'LOW'
  suggestions    : string[]
  generated_at   : string
}

// ── pre-baked example queries shown as chips ──────────────────────────────────
const EXAMPLE_QUERIES = [
  'Which vehicles crossed Ameerpet Junction in the last hour?',
  'Show vehicles between 6 PM and 7 PM',
  'How many vehicles at Begumpet in the last 2 hours?',
  'Find plate TS09AB1234',
  'Show suspicious vehicles',
  'Vehicles seen at more than 2 cameras',
  'Vehicles in the last 30 minutes',
]

const BASE_URL =
  (typeof process !== 'undefined' && process.env?.NEXT_PUBLIC_API_URL?.replace(/\/$/, '')) ||
  'http://localhost:8000'

// ── confidence badge ──────────────────────────────────────────────────────────
function ConfidenceBadge({ c }: { c: string }) {
  const colour = c === 'HIGH' ? '#1a7a55' : c === 'MEDIUM' ? '#b45309' : '#991b1b'
  const bg     = c === 'HIGH' ? '#d1fae5' : c === 'MEDIUM' ? '#fef3c7' : '#fee2e2'
  return (
    <span style={{
      display: 'inline-block', padding: '2px 8px', borderRadius: 4,
      fontSize: 9, fontWeight: 700, letterSpacing: '.5px',
      color: colour, background: bg, marginLeft: 8,
    }}>
      {c}
    </span>
  )
}

// ── intent label ──────────────────────────────────────────────────────────────
function IntentTag({ intent }: { intent: string }) {
  const labels: Record<string, string> = {
    vehicles_at_location : 'Location Query',
    count_at_location    : 'Count Query',
    plate_lookup         : 'Plate Lookup',
    time_range           : 'Time Range',
    recent               : 'Recent Activity',
    suspicious           : 'Anomaly Detection',
    multi_camera         : 'Multi-Camera Tracking',
    help                 : 'Help',
  }
  return (
    <span style={{
      display: 'inline-block', padding: '2px 9px', borderRadius: 4,
      fontSize: 9, fontWeight: 700, letterSpacing: '.5px',
      color: '#0c7f9d', background: '#e0f5fa',
    }}>
      {labels[intent] ?? intent.replace(/_/g, ' ').toUpperCase()}
    </span>
  )
}

// ── main component ────────────────────────────────────────────────────────────
export default function NaturalLanguageQuery() {
  const [question,  setQuestion]  = useState('')
  const [loading,   setLoading]   = useState(false)
  const [result,    setResult]    = useState<NLQueryResponse | null>(null)
  const [error,     setError]     = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  // focus input on mount
  useEffect(() => { inputRef.current?.focus() }, [])

  const submit = useCallback(async (q: string) => {
    const trimmed = q.trim()
    if (!trimmed || loading) return
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const res = await fetch(`${BASE_URL}/query`, {
        method : 'POST',
        headers: { 'Content-Type': 'application/json' },
        body   : JSON.stringify({ question: trimmed }),
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body.detail ?? `HTTP ${res.status}`)
      }
      const data: NLQueryResponse = await res.json()
      setResult(data)
    } catch (err) {
      setError((err as Error).message || 'Network error — is the backend running?')
    } finally {
      setLoading(false)
    }
  }, [loading])

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    submit(question)
  }

  const handleChip = (q: string) => {
    setQuestion(q)
    submit(q)
  }

  const handleReset = () => {
    setQuestion('')
    setResult(null)
    setError(null)
    setTimeout(() => inputRef.current?.focus(), 50)
  }

  return (
    <div style={{ maxWidth: 900, margin: '0 auto' }}>
      <style>{`
        .nl-chip { cursor:pointer; border:1px solid var(--border); background:#f8fafc;
          border-radius:6px; padding:6px 12px; font-size:11px; color:var(--muted-foreground);
          transition:all .15s; white-space:nowrap; }
        .nl-chip:hover { background:var(--cyan); color:#fff; border-color:var(--cyan); }
        .nl-table th { text-align:left; font-size:9px; font-weight:700; letter-spacing:.5px;
          color:var(--muted-foreground); padding:8px 12px; border-bottom:2px solid var(--border);
          text-transform:uppercase; white-space:nowrap; }
        .nl-table td { font-size:11px; padding:8px 12px; border-bottom:1px solid #f0f4f7; }
        .nl-table tr:last-child td { border-bottom:none; }
        .nl-table tr:hover td { background:#f8fafc; }
      `}</style>

      {/* ── Search bar ──────────────────────────────────────────────────────── */}
      <div className="panel" style={{ marginBottom: 18 }}>
        <div style={{ padding: '20px 22px 18px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
            <Sparkles size={18} color="var(--cyan)" />
            <span style={{ fontSize: 14, fontWeight: 600, letterSpacing: '-.3px' }}>
              Natural Language Query
            </span>
            <span style={{
              fontSize: 9, fontWeight: 700, padding: '2px 7px', borderRadius: 4,
              background: '#1a1000', color: '#b45309', letterSpacing: '.5px',
            }}>
              LIVE DATA
            </span>
          </div>
          <p style={{ fontSize: 11, color: 'var(--muted-foreground)', margin: '0 0 14px' }}>
            Ask a plain-English question about vehicle detections and traffic patterns.
          </p>

          <form onSubmit={handleSubmit} style={{ display: 'flex', gap: 10 }}>
            <div style={{ flex: 1, position: 'relative' }}>
              <Search size={15} style={{
                position: 'absolute', left: 12, top: '50%',
                transform: 'translateY(-50%)', color: 'var(--muted-foreground)',
                pointerEvents: 'none',
              }} />
              <input
                ref={inputRef}
                type="text"
                value={question}
                onChange={e => setQuestion(e.target.value)}
                placeholder='e.g. "Which vehicles crossed Ameerpet Junction in the last hour?"'
                disabled={loading}
                style={{
                  width: '100%', padding: '10px 12px 10px 36px',
                  border: '1.5px solid var(--border)', borderRadius: 8,
                  fontSize: 12, background: 'var(--card)', color: 'var(--foreground)',
                  outline: 'none', boxSizing: 'border-box',
                }}
                onFocus={e => e.target.style.borderColor = 'var(--cyan)'}
                onBlur={e  => e.target.style.borderColor = 'var(--border)'}
              />
            </div>
            <button
              type="submit"
              className="primary-button"
              disabled={loading || !question.trim()}
              style={{ padding: '10px 20px', flexShrink: 0 }}
            >
              {loading
                ? <><Loader2 size={14} style={{ animation: 'spin 1s linear infinite' }} /> Searching…</>
                : <><Search size={14} /> Ask</>
              }
            </button>
            {(result || error) && (
              <button
                type="button"
                className="date-button"
                onClick={handleReset}
                style={{ padding: '10px 14px', flexShrink: 0 }}
                title="Clear results"
              >
                <RotateCcw size={14} />
              </button>
            )}
          </form>

          {/* ── Example chips ────────────────────────────────────────────── */}
          {!result && !loading && (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 7, marginTop: 14 }}>
              {EXAMPLE_QUERIES.map(q => (
                <button
                  key={q}
                  className="nl-chip"
                  onClick={() => handleChip(q)}
                  type="button"
                >
                  {q}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* ── Error ───────────────────────────────────────────────────────────── */}
      {error && (
        <div className="panel" style={{ marginBottom: 18 }}>
          <div style={{ padding: '16px 18px', display: 'flex', gap: 12, alignItems: 'flex-start' }}>
            <AlertCircle size={18} color="var(--red)" style={{ flexShrink: 0, marginTop: 1 }} />
            <div>
              <strong style={{ fontSize: 12, color: '#a83535' }}>Query failed</strong>
              <p style={{ fontSize: 11, color: '#b94040', margin: '4px 0 0' }}>{error}</p>
            </div>
          </div>
        </div>
      )}

      {/* ── Results ─────────────────────────────────────────────────────────── */}
      {result && (
        <>
          {/* Answer card */}
          <div className="panel" style={{ marginBottom: 14 }}>
            <div style={{ padding: '16px 20px' }}>
              {/* Intent + confidence */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                <IntentTag intent={result.intent} />
                <ConfidenceBadge c={result.confidence} />
              </div>

              {/* Big answer */}
              <p style={{
                fontSize: 15, fontWeight: 600, color: 'var(--foreground)',
                margin: '0 0 8px', lineHeight: 1.4,
              }}>
                {result.answer_text}
              </p>

              {/* Interpreted as */}
              <p style={{ fontSize: 10, color: 'var(--muted-foreground)', margin: 0 }}>
                <span style={{ fontWeight: 600 }}>Interpreted as:</span>{' '}
                {result.interpreted_as}
              </p>

              {/* Params pills */}
              {Object.keys(result.parameters).length > 0 && (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 10 }}>
                  {Object.entries(result.parameters).map(([k, v]) => (
                    <span key={k} style={{
                      fontSize: 9, padding: '2px 7px', borderRadius: 4,
                      background: 'var(--muted)', color: 'var(--muted-foreground)',
                      border: '1px solid var(--border)',
                    }}>
                      {k}: <strong>{Array.isArray(v) ? (v as string[]).join(', ') : String(v)}</strong>
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Results table */}
          {result.rows.length > 0 && (
            <div className="panel" style={{ marginBottom: 14 }}>
              <div className="panel-header">
                <div>
                  <h2>Results</h2>
                  <p>
                    {result.total_results} row(s)
                    {result.rows.length < result.total_results &&
                      ` — showing ${result.rows.length}`}
                  </p>
                </div>
              </div>
              <div style={{ overflowX: 'auto', padding: '0 0 4px' }}>
                <table className="nl-table" style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr>
                      {result.columns.map(col => (
                        <th key={col}>{col.replace(/_/g, ' ')}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {result.rows.map((row, i) => (
                      <tr key={i}>
                        {result.columns.map(col => (
                          <td key={col}>
                            {col === 'status' ? (
                              <span className={`status-pill ${
                                String(row[col]).includes('IMPOSSIBLE') ? 'red' :
                                String(row[col]).includes('SUSPICIOUS') ? 'amber' : ''
                              }`}>
                                {String(row[col] ?? '—')}
                              </span>
                            ) : col === 'plate_number' ? (
                              <div className="plate">
                                <div className="plate-mark" />
                                {String(row[col] ?? '—')}
                              </div>
                            ) : (
                              String(row[col] ?? '—')
                            )}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Suggestions */}
          {result.suggestions.length > 0 && (
            <div className="panel">
              <div style={{ padding: '14px 18px' }}>
                <p style={{
                  fontSize: 10, fontWeight: 700, color: 'var(--muted-foreground)',
                  margin: '0 0 10px', letterSpacing: '.5px', textTransform: 'uppercase',
                }}>
                  Try asking
                </p>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 7 }}>
                  {result.suggestions.map(s => (
                    <button
                      key={s}
                      className="nl-chip"
                      onClick={() => handleChip(s)}
                      type="button"
                      style={{ display: 'flex', alignItems: 'center', gap: 5 }}
                    >
                      <ChevronRight size={10} />
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}
        </>
      )}

      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  )
}
