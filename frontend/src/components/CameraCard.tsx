'use client'
/**
 * CameraCard — SIH26127 UrbanEye AI
 * ====================================
 * Replaces the static placeholder camera card with a fully interactive
 * per-camera video upload and processing panel.
 *
 * Data flow:
 *   User clicks camera → modal opens → user uploads video →
 *   POST /process/video (camera_id attached) → VideoIngestResponse →
 *   buildCameraResult() → displayed in card + stored in localStorage
 *
 * Honest status labels:
 *   "No video processed"    — default, no data
 *   "Video Processed"       — real AI result available
 *   "Processing…"           — AI pipeline running
 *   "Upload Failed"         — backend error
 *
 * NO FAKE DATA. All counts come from the real VideoIngestResponse.
 * If processing hasn't happened, counts are not shown.
 */

import { useState, useRef, useCallback, useEffect } from 'react'
import {
  Camera, Upload, Play, X, AlertCircle, CheckCircle2,
  Loader2, RefreshCw, Film, CreditCard, Car, BarChart3,
  ChevronDown, ChevronUp, MapPin, Clock, Activity,
} from 'lucide-react'
import {
  processVideoForCamera, buildCameraResult,
  type CameraItem, type CameraProcessingResult, type VideoIngestResponse,
  ApiError,
} from '@/lib/api'

// ── Constants ─────────────────────────────────────────────────────────────────

const ACCEPTED_EXTS = ['.mp4', '.avi', '.mov', '.mkv']
const MAX_SIZE_BYTES = 2 * 1024 ** 3   // 2 GB

const FRAME_SKIP_OPTIONS = [
  { value: 3,  label: 'High quality (every 3rd frame)' },
  { value: 5,  label: 'Balanced (every 5th frame — default)' },
  { value: 10, label: 'Fast scan (every 10th frame)' },
]

const DENSITY_COLOUR: Record<string, string> = {
  LOW:                '#24ae76',
  MEDIUM:             '#eea524',
  HIGH:               '#e07c00',
  SEVERE:             '#db5b5d',
  INSUFFICIENT_DATA:  '#9aa8b5',
}

// ── Local storage helpers ─────────────────────────────────────────────────────

const STORAGE_KEY = 'urbaneye_camera_results'

function loadStoredResults(): Record<string, CameraProcessingResult> {
  if (typeof window === 'undefined') return {}
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) : {}
  } catch { return {} }
}

function saveResult(result: CameraProcessingResult) {
  if (typeof window === 'undefined') return
  try {
    const all = loadStoredResults()
    all[result.camera_id] = result
    localStorage.setItem(STORAGE_KEY, JSON.stringify(all))
  } catch { /* quota exceeded — silently ignore */ }
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtBytes(b: number): string {
  if (b < 1024) return `${b} B`
  if (b < 1024 ** 2) return `${(b / 1024).toFixed(1)} KB`
  if (b < 1024 ** 3) return `${(b / 1024 ** 2).toFixed(1)} MB`
  return `${(b / 1024 ** 3).toFixed(2)} GB`
}

function fmtTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString()
  } catch { return iso }
}

function fmtDuration(totalFrames: number, fps = 25): string {
  const secs = Math.round(totalFrames / fps)
  const m = Math.floor(secs / 60)
  const s = secs % 60
  return m > 0 ? `${m}m ${s}s` : `${s}s`
}

// ── Upload progress stages ────────────────────────────────────────────────────

const STAGES = [
  { id: 'uploading', label: 'Uploading video'         },
  { id: 'detecting', label: 'Detecting vehicles'       },
  { id: 'plates',    label: 'Detecting plates'         },
  { id: 'ocr',       label: 'Extracting plate text'    },
  { id: 'analytics', label: 'Building analytics'       },
] as const
type StageId = typeof STAGES[number]['id']

// ═══════════════════════════════════════════════════════════════════════════════
// CAMERA CARD MODAL
// ═══════════════════════════════════════════════════════════════════════════════

interface ModalProps {
  camera     : CameraItem
  stored     : CameraProcessingResult | null
  onClose    : () => void
  onResult   : (r: CameraProcessingResult) => void
}

function CameraModal({ camera, stored, onClose, onResult }: ModalProps) {
  const [file,       setFile]       = useState<File | null>(null)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [fileError,  setFileError]  = useState<string | null>(null)
  const [frameSkip,  setFrameSkip]  = useState(5)
  const [uploadPct,  setUploadPct]  = useState(0)
  const [stage,      setStage]      = useState<StageId | null>(null)
  const [doneStages, setDoneStages] = useState<Set<StageId>>(new Set())
  const [processing, setProcessing] = useState(false)
  const [errorMsg,   setErrorMsg]   = useState<string | null>(null)
  const [result,     setResult]     = useState<CameraProcessingResult | null>(stored)
  const fileRef = useRef<HTMLInputElement>(null)
  const stageTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => () => {
    if (previewUrl) URL.revokeObjectURL(previewUrl)
    if (stageTimerRef.current) clearTimeout(stageTimerRef.current)
  }, [previewUrl])

  const onFileChange = useCallback((f: File) => {
    const ext = '.' + f.name.split('.').pop()!.toLowerCase()
    if (!ACCEPTED_EXTS.includes(ext)) {
      setFileError(`Unsupported format "${ext}". Accepted: ${ACCEPTED_EXTS.join(', ')}`)
      return
    }
    if (f.size > MAX_SIZE_BYTES) {
      setFileError(`File too large (${fmtBytes(f.size)}). Max: 2 GB`)
      return
    }
    setFileError(null)
    setErrorMsg(null)
    setFile(f)
    if (previewUrl) URL.revokeObjectURL(previewUrl)
    setPreviewUrl(URL.createObjectURL(f))
  }, [previewUrl])

  const advanceStages = useCallback(async () => {
    const remaining: StageId[] = ['detecting', 'plates', 'ocr', 'analytics']
    for (const s of remaining) {
      setStage(s)
      await new Promise<void>(r => { stageTimerRef.current = setTimeout(r, 1800) })
      setDoneStages(prev => new Set([...prev, s]))
    }
    setStage(null)
  }, [])

  const handleProcess = useCallback(async () => {
    if (!file || processing) return
    setProcessing(true)
    setErrorMsg(null)
    setResult(null)
    setDoneStages(new Set())
    setStage('uploading')
    setUploadPct(0)

    let stagesStarted = false

    try {
      const [resp] = await Promise.all([
        processVideoForCamera(file, camera.camera_id, frameSkip, (pct) => {
          setUploadPct(pct)
          if (pct >= 100 && !stagesStarted) {
            stagesStarted = true
            setDoneStages(prev => new Set([...prev, 'uploading']))
            setStage('detecting')
            advanceStages()
          }
        }),
      ])

      setDoneStages(new Set(STAGES.map(s => s.id)))
      setStage(null)

      const r = buildCameraResult(resp, camera.camera_id)
      saveResult(r)
      setResult(r)
      onResult(r)
    } catch (err) {
      const msg = err instanceof ApiError
        ? err.detail
        : `Processing failed: ${(err as Error).message}`
      setErrorMsg(msg)
      setStage(null)
    } finally {
      setProcessing(false)
    }
  }, [file, processing, camera.camera_id, frameSkip, advanceStages, onResult])

  return (
    <div
      style={{
        position: 'fixed', inset: 0, zIndex: 1000,
        background: 'rgba(7,19,35,.75)', backdropFilter: 'blur(3px)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        padding: '20px',
      }}
      onClick={e => { if (e.target === e.currentTarget) onClose() }}
    >
      <div style={{
        background: 'var(--card)', borderRadius: 10, width: '100%', maxWidth: 820,
        maxHeight: 'calc(100vh - 40px)', overflowY: 'auto',
        boxShadow: '0 24px 48px rgba(0,0,0,.35)',
      }}>
        {/* Header */}
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '18px 22px 14px', borderBottom: '1px solid var(--border)',
        }}>
          <div>
            <h2 style={{ margin: 0, fontSize: 16, letterSpacing: '-.3px' }}>
              {camera.camera_id} — {camera.location_name}
            </h2>
            <p style={{ margin: '3px 0 0', fontSize: 11, color: 'var(--muted-foreground)' }}>
              {camera.road_name || 'Hyderabad, India'} · {camera.latitude.toFixed(4)}°N {camera.longitude.toFixed(4)}°E
            </p>
          </div>
          <button
            onClick={onClose}
            style={{ border: 0, background: 'transparent', cursor: 'pointer', color: '#9aa8b5', padding: 4 }}
          >
            <X size={18} />
          </button>
        </div>

        <div style={{ padding: '20px 22px' }}>
          {/* Camera info row */}
          <div style={{
            display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 10,
            padding: '12px 16px', background: 'var(--muted)',
            borderRadius: 8, marginBottom: 20, fontSize: 10,
          }}>
            {[
              ['Camera ID',  camera.camera_id],
              ['Location',   camera.location_name],
              ['Direction',  camera.direction?.replace(/_/g, ' ') || '—'],
              ['Latitude',   camera.latitude.toFixed(4) + '°N'],
              ['Longitude',  camera.longitude.toFixed(4) + '°E'],
              ['Source',     result ? 'Uploaded Video' : 'No video processed'],
            ].map(([k, v]) => (
              <div key={k}>
                <span style={{ color: 'var(--muted-foreground)', display: 'block' }}>{k}</span>
                <strong style={{ fontSize: 11, color: 'var(--foreground)' }}>{v}</strong>
              </div>
            ))}
          </div>

          {/* Status pill */}
          <div style={{ marginBottom: 16 }}>
            {!result && !processing && (
              <span style={{
                display: 'inline-flex', alignItems: 'center', gap: 5,
                padding: '4px 10px', borderRadius: 12,
                background: 'var(--muted)', color: '#6d7f92', fontSize: 10, fontWeight: 700,
              }}>
                <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#9aa8b5', display: 'inline-block' }} />
                No live source connected · Upload a video to analyse this camera
              </span>
            )}
            {processing && (
              <span style={{
                display: 'inline-flex', alignItems: 'center', gap: 5,
                padding: '4px 10px', borderRadius: 12,
                background: '#e4f5f9', color: 'var(--primary)', fontSize: 10, fontWeight: 700,
              }}>
                <Loader2 size={10} style={{ animation: 'spin 1s linear infinite' }} />
                Processing video…
                <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
              </span>
            )}
            {result && !processing && (
              <span style={{
                display: 'inline-flex', alignItems: 'center', gap: 5,
                padding: '4px 10px', borderRadius: 12,
                background: '#021a0f', color: '#169266', fontSize: 10, fontWeight: 700,
              }}>
                <CheckCircle2 size={10} />
                Video Processed · {fmtTime(result.processed_at)}
              </span>
            )}
          </div>

          {/* Upload zone */}
          {!processing && (
            <div style={{ marginBottom: 20 }}>
              <p style={{ fontSize: 11, fontWeight: 700, marginBottom: 8, color: 'var(--foreground)' }}>
                {file ? 'Selected video' : 'Upload a traffic video for this camera'}
              </p>

              {!file ? (
                <div
                  style={{
                    border: '2px dashed var(--border)', borderRadius: 8,
                    padding: '28px', textAlign: 'center', cursor: 'pointer',
                    background: 'var(--muted)',
                  }}
                  onClick={() => fileRef.current?.click()}
                  onDragOver={e => e.preventDefault()}
                  onDrop={e => { e.preventDefault(); const f = e.dataTransfer.files[0]; if (f) onFileChange(f) }}
                >
                  <Film size={28} color="#9aa8b5" style={{ margin: '0 auto 10px', display: 'block' }} />
                  <p style={{ margin: 0, fontSize: 12, color: 'var(--muted-foreground)' }}>
                    Drop a video here or <span style={{ color: 'var(--primary)', fontWeight: 700 }}>browse</span>
                  </p>
                  <p style={{ margin: '6px 0 0', fontSize: 10, color: '#9aa8b5' }}>
                    MP4 · AVI · MOV · MKV · Max 2 GB
                  </p>
                </div>
              ) : (
                <div style={{ border: '1px solid var(--border)', borderRadius: 8, overflow: 'hidden' }}>
                  {previewUrl && (
                    <video
                      src={previewUrl}
                      controls
                      style={{ width: '100%', maxHeight: 200, display: 'block', background: '#0d1c2d' }}
                      preload="metadata"
                    />
                  )}
                  <div style={{ padding: '10px 14px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div style={{ fontSize: 11 }}>
                      <strong>{file.name}</strong>
                      <span style={{ color: 'var(--muted-foreground)', marginLeft: 8 }}>{fmtBytes(file.size)}</span>
                    </div>
                    <button
                      onClick={() => { setFile(null); if (previewUrl) URL.revokeObjectURL(previewUrl); setPreviewUrl(null) }}
                      style={{ border: 0, background: 'transparent', color: '#9aa8b5', cursor: 'pointer', padding: 2 }}
                    >
                      <X size={14} />
                    </button>
                  </div>
                </div>
              )}

              <input
                ref={fileRef}
                type="file"
                accept={ACCEPTED_EXTS.join(',')}
                style={{ display: 'none' }}
                onChange={e => { const f = e.target.files?.[0]; if (f) onFileChange(f); e.target.value = '' }}
              />
              {fileError && (
                <p style={{ fontSize: 10, color: '#b94040', marginTop: 6, display: 'flex', alignItems: 'center', gap: 4 }}>
                  <AlertCircle size={11} /> {fileError}
                </p>
              )}

              {/* Frame skip selector */}
              {file && (
                <div style={{ marginTop: 12 }}>
                  <label style={{ fontSize: 10, color: 'var(--muted-foreground)', fontWeight: 700, letterSpacing: '.5px' }}>
                    FRAME SAMPLING
                  </label>
                  <select
                    value={frameSkip}
                    onChange={e => setFrameSkip(Number(e.target.value))}
                    style={{
                      width: '100%', marginTop: 5, padding: '8px 10px',
                      border: '1px solid var(--border)', borderRadius: 6,
                      background: 'var(--card)', fontSize: 11, cursor: 'pointer',
                    }}
                  >
                    {FRAME_SKIP_OPTIONS.map(o => (
                      <option key={o.value} value={o.value}>{o.label}</option>
                    ))}
                  </select>
                  <p style={{ fontSize: 9, color: 'var(--muted-foreground)', marginTop: 4 }}>
                    Lower frame skip = more detections, slower. Recommended: every 3rd–5th frame.
                  </p>
                </div>
              )}
            </div>
          )}

          {/* Pipeline stages */}
          {processing && (
            <div style={{ marginBottom: 20 }}>
              <p style={{ fontSize: 11, fontWeight: 700, marginBottom: 10, color: 'var(--foreground)' }}>
                Processing pipeline
              </p>
              {/* Upload progress bar */}
              {uploadPct < 100 && stage === 'uploading' && (
                <div style={{ marginBottom: 10 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 9, color: 'var(--muted-foreground)', marginBottom: 3 }}>
                    <span>Uploading to backend…</span><span>{uploadPct}%</span>
                  </div>
                  <div style={{ height: 4, background: '#1a2f44', borderRadius: 3, overflow: 'hidden' }}>
                    <div style={{ height: '100%', background: 'var(--cyan)', borderRadius: 3, width: `${uploadPct}%`, transition: 'width .3s' }} />
                  </div>
                </div>
              )}
              {STAGES.map(s => {
                const isDone   = doneStages.has(s.id)
                const isActive = stage === s.id
                return (
                  <div key={s.id} style={{
                    display: 'flex', alignItems: 'center', gap: 10,
                    padding: '8px 0', borderBottom: '1px solid #f0f4f7',
                    opacity: (!isDone && !isActive) ? .4 : 1,
                  }}>
                    <div style={{
                      width: 26, height: 26, borderRadius: 6, display: 'grid', placeItems: 'center', flexShrink: 0,
                      background: isDone ? '#dff5ec' : isActive ? '#e4f5f9' : '#f0f4f7',
                      color:      isDone ? '#24ae76' : isActive ? 'var(--primary)' : '#9aa8b5',
                    }}>
                      {isActive
                        ? <Loader2 size={13} style={{ animation: 'spin 1s linear infinite' }} />
                        : isDone
                        ? <CheckCircle2 size={13} />
                        : <Activity size={13} />
                      }
                    </div>
                    <span style={{ fontSize: 12, fontWeight: isActive ? 600 : 400 }}>{s.label}</span>
                    {isDone && <span style={{ marginLeft: 'auto', fontSize: 9, color: '#24ae76', fontWeight: 700 }}>DONE</span>}
                    {isActive && <span style={{ marginLeft: 'auto', fontSize: 9, color: 'var(--primary)', fontWeight: 700 }}>RUNNING</span>}
                  </div>
                )
              })}
            </div>
          )}

          {/* Error */}
          {errorMsg && (
            <div style={{
              display: 'flex', alignItems: 'flex-start', gap: 8,
              padding: '12px 14px', background: '#1a0508', borderRadius: 8, marginBottom: 16,
            }}>
              <AlertCircle size={15} color="#b94040" style={{ flexShrink: 0, marginTop: 1 }} />
              <div>
                <strong style={{ display: 'block', fontSize: 12, color: '#a83535' }}>Processing failed</strong>
                <p style={{ margin: 0, fontSize: 11, color: '#b94040' }}>{errorMsg}</p>
              </div>
            </div>
          )}

          {/* Results */}
          {result && !processing && (
            <div style={{ marginBottom: 16 }}>
              <p style={{ fontSize: 11, fontWeight: 700, marginBottom: 12, color: 'var(--foreground)' }}>
                Real Processing Results
              </p>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 10, marginBottom: 14 }}>
                {[
                  { label: 'Vehicles detected', value: result.total_detections,  colour: 'cyan-bg',   icon: Car },
                  { label: 'Verified plates',   value: result.verified_count,   colour: 'green-bg',  icon: CreditCard },
                  { label: 'Partial reads',     value: result.partial_count,    colour: 'amber-bg',  icon: AlertCircle },
                  { label: 'Frames processed',  value: result.frames_processed,  colour: 'purple-bg', icon: Film },
                ].map(({ label, value, colour, icon: Icon }) => (
                  <article className="kpi-card" key={label} style={{ padding: '12px 14px' }}>
                    <span className={`kpi-icon ${colour}`} style={{ width: 26, height: 26, borderRadius: 6 }}>
                      <Icon size={13} />
                    </span>
                    <strong style={{ display: 'block', fontSize: 20, marginTop: 10, letterSpacing: '-.5px' }}>{value}</strong>
                    <span className="kpi-label" style={{ fontSize: 10 }}>{label}</span>
                  </article>
                ))}
              </div>

              {/* Vehicle types */}
              {Object.keys(result.vehicle_type_counts).length > 0 && (
                <div style={{ marginBottom: 14 }}>
                  <p style={{ fontSize: 10, fontWeight: 700, color: 'var(--muted-foreground)', marginBottom: 8 }}>VEHICLE TYPES</p>
                  {Object.entries(result.vehicle_type_counts)
                    .sort((a, b) => b[1] - a[1])
                    .map(([type, count]) => (
                      <div key={type} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                        <span style={{ fontSize: 11, textTransform: 'capitalize', width: 90 }}>{type}</span>
                        <div style={{ flex: 1, height: 5, background: '#1a2f44', borderRadius: 3, overflow: 'hidden' }}>
                          <div style={{
                            height: '100%', borderRadius: 3,
                            background: type === 'car' ? 'var(--cyan)' : type === 'motorcycle' ? 'var(--amber)' :
                                        type === 'bus' ? 'var(--green)' : type === 'truck' ? 'var(--purple)' : '#b0bec8',
                            width: `${Math.round(count / result.total_detections * 100)}%`,
                          }} />
                        </div>
                        <span style={{ fontSize: 10, color: 'var(--muted-foreground)', minWidth: 36, textAlign: 'right' }}>{count}</span>
                      </div>
                    ))}
                </div>
              )}

              {/* Traffic density */}
              <div style={{ padding: '10px 14px', background: 'var(--muted)', borderRadius: 8, marginBottom: 12 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div>
                    <p style={{ fontSize: 10, fontWeight: 700, color: 'var(--muted-foreground)', margin: '0 0 3px' }}>
                      TRAFFIC DENSITY
                    </p>
                    <strong style={{ fontSize: 16, color: DENSITY_COLOUR[result.density_level] }}>
                      {result.density_level.replace('_', ' ')}
                    </strong>
                    {result.vehicles_per_minute !== null && (
                      <p style={{ fontSize: 10, color: 'var(--muted-foreground)', margin: '2px 0 0' }}>
                        {result.vehicles_per_minute} vehicles/min · {fmtDuration(result.total_frames)} video
                      </p>
                    )}
                  </div>
                  <BarChart3 size={28} color={DENSITY_COLOUR[result.density_level]} style={{ opacity: .6 }} />
                </div>
                <p style={{ fontSize: 9, color: '#9aa8b5', margin: '6px 0 0', fontStyle: 'italic' }}>
                  {result.formula_note}
                </p>
              </div>

              {/* Verified plates */}
              {result.verified_plates.length > 0 && (
                <div style={{ marginBottom: 12 }}>
                  <p style={{ fontSize: 10, fontWeight: 700, color: 'var(--muted-foreground)', marginBottom: 6 }}>
                    VERIFIED PLATES
                  </p>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                    {result.verified_plates.map(p => (
                      <span key={p} style={{
                        padding: '3px 8px', borderRadius: 5,
                        background: '#e4f5f9', color: 'var(--primary)',
                        fontSize: 10, fontWeight: 700, border: '1px solid #b0e0ef',
                      }}>{p}</span>
                    ))}
                  </div>
                </div>
              )}

              {/* Partial plates */}
              {result.partial_plates.length > 0 && (
                <div style={{ marginBottom: 12 }}>
                  <p style={{ fontSize: 10, fontWeight: 700, color: 'var(--muted-foreground)', marginBottom: 6 }}>
                    PARTIAL READS (not verified)
                  </p>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                    {result.partial_plates.map(p => (
                      <span key={p} style={{
                        padding: '3px 8px', borderRadius: 5,
                        background: '#1a1000', color: '#c28118',
                        fontSize: 10, fontWeight: 700, border: '1px solid #f8d38b',
                      }}>{p}</span>
                    ))}
                  </div>
                  <p style={{ fontSize: 9, color: '#c28118', margin: '4px 0 0', fontStyle: 'italic' }}>
                    Partial OCR — not confirmed as complete plate numbers
                  </p>
                </div>
              )}

              {/* Source info */}
              <div style={{ padding: '8px 14px', background: 'var(--muted)', borderRadius: 8, fontSize: 10 }}>
                <p style={{ margin: '0 0 4px', color: 'var(--muted-foreground)', fontWeight: 700 }}>PROCESSING INFO</p>
                {[
                  ['Source file',     result.source_file],
                  ['Processed at',    fmtTime(result.processed_at)],
                  ['Frame skip',      `every ${result.frame_skip}th frame`],
                  ['Total frames',    String(result.total_frames)],
                  ['Frames analysed', String(result.frames_processed)],
                ].map(([k, v]) => (
                  <div key={k} style={{ display: 'flex', justifyContent: 'space-between', padding: '3px 0', borderBottom: '1px solid #edf1f4' }}>
                    <span style={{ color: 'var(--muted-foreground)' }}>{k}</span>
                    <strong style={{ maxWidth: 200, textAlign: 'right', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{v}</strong>
                  </div>
                ))}
              </div>
              {result.warnings.length > 0 && (
                <div style={{ padding: '8px 12px', background: '#1a1200', borderRadius: 6, marginTop: 8 }}>
                  {result.warnings.map((w, i) => (
                    <p key={i} style={{ fontSize: 9, color: '#c28118', margin: '2px 0' }}>⚠ {w}</p>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Action buttons */}
          <div style={{ display: 'flex', gap: 10 }}>
            {file && !processing && (
              <button
                className="primary-button"
                style={{ fontSize: 13, padding: '10px 22px' }}
                onClick={handleProcess}
              >
                <Play size={14} /> Process Video
              </button>
            )}
            {result && !file && !processing && (
              <button
                className="date-button"
                onClick={() => fileRef.current?.click()}
                style={{ fontSize: 11 }}
              >
                <RefreshCw size={12} /> Reprocess with new video
              </button>
            )}
            {!file && !result && !processing && (
              <button
                className="primary-button"
                onClick={() => fileRef.current?.click()}
                style={{ fontSize: 13, padding: '10px 22px' }}
              >
                <Upload size={14} /> Choose Video
              </button>
            )}
            <button className="date-button" onClick={onClose} style={{ fontSize: 11 }}>
              <X size={12} /> Close
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// CAMERA CARD (inline display in the camera grid)
// ═══════════════════════════════════════════════════════════════════════════════

interface CameraCardProps {
  camera  : CameraItem
  stored  : CameraProcessingResult | null
  onUpdate: (r: CameraProcessingResult) => void
}

export function CameraCard({ camera, stored, onUpdate }: CameraCardProps) {
  const [open, setOpen] = useState(false)

  const densityColour = stored ? DENSITY_COLOUR[stored.density_level] : '#9aa8b5'

  return (
    <>
      {/* ── Inline card ───────────────────────────────────────────────── */}
      <article className="panel" style={{ cursor: 'pointer', transition: 'box-shadow .2s' }}
        onClick={() => setOpen(true)}
        onMouseEnter={e => (e.currentTarget.style.boxShadow = '0 0 0 2px var(--primary)')}
        onMouseLeave={e => (e.currentTarget.style.boxShadow = '')}
      >
        <div className="panel-header">
          <div style={{ minWidth: 0 }}>
            <h2 style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {camera.camera_id}
            </h2>
            <p style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {camera.location_name}
            </p>
          </div>
          {/* Status indicator */}
          {stored
            ? <span style={{ fontSize: 9, fontWeight: 700, color: '#169266', background: '#021a0f', padding: '2px 7px', borderRadius: 10, whiteSpace: 'nowrap' }}>
                ✓ Processed
              </span>
            : <span style={{ fontSize: 9, fontWeight: 700, color: '#9aa8b5', background: 'var(--muted)', padding: '2px 7px', borderRadius: 10, whiteSpace: 'nowrap' }}>
                No video
              </span>
          }
        </div>

        <div style={{ padding: '12px 18px 16px' }}>
          {/* Preview area */}
          <div style={{
            height: 110, background: 'var(--navy)', borderRadius: 6,
            display: 'grid', placeItems: 'center', marginBottom: 10,
            color: 'var(--cyan)', position: 'relative',
          }}>
            <Camera size={28} />
            <div style={{
              position: 'absolute', bottom: 8, left: 0, right: 0,
              textAlign: 'center', fontSize: 9, color: '#4a6a88',
            }}>
              {stored ? stored.source_file : 'Click to upload & process video'}
            </div>
          </div>

          {/* Stats row */}
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10 }}>
            <span style={{ color: 'var(--muted-foreground)' }}>
              {stored
                ? `${stored.total_detections} detections`
                : 'Demo camera config'}
            </span>
            <span style={{
              fontWeight: 700, color: densityColour,
            }}>
              {stored
                ? stored.density_level.replace('_', ' ')
                : 'No live source'}
            </span>
          </div>

          {/* Road name */}
          {camera.road_name && (
            <p style={{ fontSize: 10, color: 'var(--muted-foreground)', marginTop: 5 }}>
              {camera.road_name}
            </p>
          )}

          {/* Quick plate count */}
          {stored && stored.verified_count > 0 && (
            <p style={{ fontSize: 10, color: '#169266', marginTop: 4, fontWeight: 700 }}>
              {stored.verified_count} verified plate{stored.verified_count !== 1 ? 's' : ''}
            </p>
          )}

          {/* Click prompt */}
          <div style={{
            marginTop: 8, display: 'flex', alignItems: 'center', gap: 5,
            fontSize: 10, color: 'var(--primary)', fontWeight: 700,
          }}>
            <Upload size={11} />
            {stored ? 'Click to view details / reprocess' : 'Click to upload video'}
          </div>
        </div>
      </article>

      {/* ── Modal ────────────────────────────────────────────────────── */}
      {open && (
        <CameraModal
          camera={camera}
          stored={stored}
          onClose={() => setOpen(false)}
          onResult={r => { onUpdate(r); setOpen(false) }}
        />
      )}
    </>
  )
}

// ── Export storage helpers for the CameraNetwork page ─────────────────────────
export { loadStoredResults, saveResult }
