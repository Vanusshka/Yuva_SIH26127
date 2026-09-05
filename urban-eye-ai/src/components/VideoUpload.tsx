'use client'
/**
 * VideoUpload — SIH26127 UrbanEye AI
 * ====================================
 * Full video upload & processing feature.
 *
 * Backend endpoint used: POST /process/video  (Phase 7, already exists)
 * Response type: VideoIngestResponse
 *
 * Stages shown during processing:
 *   Uploading video → Detecting vehicles → Tracking vehicles →
 *   Detecting number plates → Extracting plate text → Generating analytics
 *
 * All result data comes from the real backend — no fake/mock values.
 */

import { useState, useRef, useCallback, useEffect } from 'react'
import {
  Upload, Film, X, Play, CheckCircle2, AlertCircle,
  Car, CreditCard, Activity, Clock, ChevronRight,
  Loader2, BarChart3, Eye, RefreshCw, Download,
} from 'lucide-react'
import {
  processVideo,
  type VideoIngestResponse,
  type IngestDetection,
  ApiError,
} from '@/lib/api'

// ── constants ─────────────────────────────────────────────────────────────────

const STORAGE_KEY = 'urbanEye_videoUpload_v1'

/** Serialisable subset of state persisted to sessionStorage */
interface PersistedState {
  fileName    : string
  fileSize    : number
  cameraId    : string
  frameSkip   : number
  uploadState : UploadState
  elapsedSec  : number
  result      : VideoIngestResponse | null
}

const ACCEPTED = ['.mp4', '.avi', '.mov', '.mkv']
const MAX_SIZE_GB = 2
const MAX_SIZE_BYTES = MAX_SIZE_GB * 1024 ** 3

const CAMERAS = [
  'CAM_001', 'CAM_002', 'CAM_003', 'CAM_004', 'CAM_005',
  'CAM_006', 'CAM_007', 'CAM_008', 'CAM_009', 'CAM_010',
]

const FRAME_SKIP_OPTIONS = [
  { value: 2,  label: 'Max quality   (every 2nd frame — slowest)' },
  { value: 3,  label: 'High quality  (every 3rd frame — recommended)' },
  { value: 5,  label: 'Balanced      (every 5th frame)' },
  { value: 10, label: 'Fast preview  (every 10th frame — quickest)' },
]

/** Processing pipeline stages */
const STAGES = [
  { id: 'uploading',   label: 'Uploading video',          icon: Upload },
  { id: 'vehicles',    label: 'Detecting vehicles',        icon: Car },
  { id: 'tracking',    label: 'Tracking vehicles',         icon: Eye },
  { id: 'plates',      label: 'Detecting number plates',   icon: CreditCard },
  { id: 'ocr',         label: 'Extracting plate text',     icon: Activity },
  { id: 'analytics',   label: 'Generating analytics',      icon: BarChart3 },
] as const

type StageId = typeof STAGES[number]['id']
type UploadState = 'idle' | 'processing' | 'done' | 'error'

// ── helpers ───────────────────────────────────────────────────────────────────

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`
  return `${(bytes / 1024 ** 3).toFixed(2)} GB`
}

function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = Math.round(seconds % 60)
  return m > 0 ? `${m}m ${s}s` : `${s}s`
}

function formatTime(iso: string): string {
  try { return new Date(iso).toLocaleTimeString() } catch { return iso }
}

// ── sub-components ────────────────────────────────────────────────────────────

function StageRow({
  stage, state,
}: {
  stage: typeof STAGES[number]
  state: 'waiting' | 'active' | 'done'
}) {
  const Icon = stage.icon
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 12,
      padding: '10px 0',
      borderBottom: '1px solid var(--border)',
      opacity: state === 'waiting' ? 0.4 : 1,
      transition: 'opacity .3s',
    }}>
      <div style={{
        width: 30, height: 30, borderRadius: 7, display: 'grid', placeItems: 'center',
        background: state === 'done'   ? '#dff5ec' :
                    state === 'active' ? '#dcf4fa' : '#f0f4f7',
        color:      state === 'done'   ? 'var(--green)' :
                    state === 'active' ? 'var(--cyan)'  : '#b0bec8',
        flexShrink: 0,
      }}>
        {state === 'active'
          ? <Loader2 size={15} style={{ animation: 'spin 1s linear infinite' }} />
          : state === 'done'
          ? <CheckCircle2 size={15} />
          : <Icon size={15} />
        }
      </div>
      <span style={{ flex: 1, fontSize: 12, fontWeight: state === 'active' ? 600 : 400 }}>
        {stage.label}
      </span>
      {state === 'done' && (
        <span style={{ fontSize: 9, color: 'var(--green)', fontWeight: 700, letterSpacing: '.5px' }}>
          DONE
        </span>
      )}
      {state === 'active' && (
        <span style={{ fontSize: 9, color: 'var(--cyan)', fontWeight: 700, letterSpacing: '.5px' }}>
          RUNNING
        </span>
      )}
    </div>
  )
}

function PlateChip({ plate, lowConf }: { plate: string; lowConf?: boolean }) {
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 5,
      padding: '4px 9px', borderRadius: 5,
      background: lowConf ? '#fff3dd' : '#e4f5f9',
      color:      lowConf ? '#c28118' : '#0c7f9d',
      fontWeight: 700, fontSize: 10, letterSpacing: '.3px',
      border: `1px solid ${lowConf ? '#f8d38b' : '#b0e0ef'}`,
    }}>
      {lowConf && <AlertCircle size={10} />}
      {plate}
    </span>
  )
}

// ── main component ────────────────────────────────────────────────────────────

export default function VideoUpload() {
  // File state
  const [file,         setFile]         = useState<File | null>(null)
  const [previewUrl,   setPreviewUrl]   = useState<string | null>(null)
  const [dragOver,     setDragOver]     = useState(false)
  const [fileError,    setFileError]    = useState<string | null>(null)

  // Config
  const [cameraId,     setCameraId]     = useState('CAM_001')
  const [frameSkip,    setFrameSkip]    = useState(3)

  // Processing state
  const [uploadState,  setUploadState]  = useState<UploadState>('idle')
  const [uploadPct,    setUploadPct]    = useState(0)
  const [activeStage,  setActiveStage]  = useState<StageId | null>(null)
  const [doneStages,   setDoneStages]   = useState<Set<StageId>>(new Set())
  const [startTime,    setStartTime]    = useState<number | null>(null)
  const [elapsedSec,   setElapsedSec]   = useState(0)
  const [errorMsg,     setErrorMsg]     = useState<string | null>(null)

  // Results
  const [result,       setResult]       = useState<VideoIngestResponse | null>(null)

  // Refs
  const fileInputRef = useRef<HTMLInputElement>(null)
  const timerRef     = useRef<ReturnType<typeof setInterval> | null>(null)

  // ── Restore persisted state on mount ─────────────────────────────────────
  useEffect(() => {
    try {
      const raw = sessionStorage.getItem(STORAGE_KEY)
      if (!raw) return
      const saved: PersistedState = JSON.parse(raw)
      // Restore the serialisable fields
      setCameraId(saved.cameraId)
      setFrameSkip(saved.frameSkip)
      setElapsedSec(saved.elapsedSec ?? 0)
      if (saved.result && (saved.uploadState === 'done' || saved.uploadState === 'error')) {
        setResult(saved.result)
        setUploadState(saved.uploadState)
        // Restore minimal file info for the "Processing Info" panel
        // File object itself cannot be restored — show info from result
      }
    } catch {
      // Corrupt storage — ignore
      sessionStorage.removeItem(STORAGE_KEY)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])   // run once on mount only

  // ── Persist serialisable state on every relevant change ──────────────────
  useEffect(() => {
    // Only persist when there is something worth saving
    if (uploadState === 'idle' && !result) return
    try {
      const toSave: PersistedState = {
        fileName   : file?.name ?? result?.source_file ?? '',
        fileSize   : file?.size ?? 0,
        cameraId,
        frameSkip,
        uploadState,
        elapsedSec,
        result,
      }
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(toSave))
    } catch {
      // Storage full or unavailable — ignore
    }
  }, [uploadState, result, cameraId, frameSkip, elapsedSec, file])

  // Cleanup preview URL on unmount
  useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl)
      if (timerRef.current) clearInterval(timerRef.current)
    }
  }, [previewUrl])

  // Elapsed time ticker
  useEffect(() => {
    if (uploadState === 'processing' && startTime !== null) {
      timerRef.current = setInterval(() => {
        setElapsedSec(Math.floor((Date.now() - startTime) / 1000))
      }, 1000)
    } else {
      if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null }
    }
    return () => { if (timerRef.current) clearInterval(timerRef.current) }
  }, [uploadState, startTime])

  // ── file validation ──────────────────────────────────────────────────────

  const validateAndSetFile = useCallback((f: File) => {
    setFileError(null)
    const ext = '.' + f.name.split('.').pop()!.toLowerCase()
    if (!ACCEPTED.includes(ext)) {
      setFileError(`Unsupported format "${ext}". Accepted: ${ACCEPTED.join(', ')}`)
      return
    }
    if (f.size > MAX_SIZE_BYTES) {
      setFileError(`File too large (${formatBytes(f.size)}). Maximum: ${MAX_SIZE_GB} GB`)
      return
    }
    if (previewUrl) URL.revokeObjectURL(previewUrl)
    setFile(f)
    setPreviewUrl(URL.createObjectURL(f))
    setResult(null)
    setUploadState('idle')
    setErrorMsg(null)
    setDoneStages(new Set())
    setActiveStage(null)
  }, [previewUrl])

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    const f = e.dataTransfer.files[0]
    if (f) validateAndSetFile(f)
  }, [validateAndSetFile])

  const onFileInput = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]
    if (f) validateAndSetFile(f)
    e.target.value = ''
  }, [validateAndSetFile])

  const clearFile = useCallback(() => {
    if (previewUrl) URL.revokeObjectURL(previewUrl)
    setFile(null)
    setPreviewUrl(null)
    setResult(null)
    setUploadState('idle')
    setErrorMsg(null)
    setFileError(null)
    setDoneStages(new Set())
    setActiveStage(null)
    sessionStorage.removeItem(STORAGE_KEY)
  }, [previewUrl])

  // ── processing pipeline ──────────────────────────────────────────────────

  /**
   * Simulates the multi-stage progress display while the real XHR runs.
   * Stages after 'uploading' are time-estimated because the backend doesn't
   * stream stage events — the real work happens server-side.
   */
  const runStageAnimation = useCallback(async (totalFrames?: number) => {
    const estimate = (totalFrames ?? 300) / Math.max(frameSkip, 1)

    // After upload completes, step through remaining stages based on frame count
    // Each stage gets ~(estimate / 5) seconds minimum, capped at 30s each
    const stageMs = Math.min(Math.max((estimate / 5) * 1000, 1200), 30_000)

    const remaining: StageId[] = ['vehicles', 'tracking', 'plates', 'ocr', 'analytics']

    for (const stage of remaining) {
      setActiveStage(stage)
      await new Promise<void>(r => setTimeout(r, stageMs))
      setDoneStages(prev => new Set([...prev, stage]))
    }
    setActiveStage(null)
  }, [frameSkip])

  const handleProcess = useCallback(async () => {
    if (!file || uploadState === 'processing') return

    setUploadState('processing')
    setErrorMsg(null)
    setResult(null)
    setDoneStages(new Set())
    setActiveStage('uploading')
    setUploadPct(0)
    setStartTime(Date.now())
    setElapsedSec(0)

    try {
      // Fire both the real API call and the stage animation in parallel.
      // The API call drives the actual result; the animation drives the UI.
      const [apiResult] = await Promise.all([
        processVideo(file, cameraId, frameSkip, (pct) => {
          setUploadPct(pct)
          if (pct === 100) {
            setDoneStages(prev => new Set([...prev, 'uploading']))
            setActiveStage('vehicles')
          }
        }),
        // Stage animation resolves independently — won't block the real result
        new Promise<void>(resolve => {
          // Wait for upload to complete (pct hits 100) then animate stages
          const poll = setInterval(() => {
            setUploadPct(prev => {
              if (prev >= 100) {
                clearInterval(poll)
                resolve()
              }
              return prev
            })
          }, 200)
        }).then(() => runStageAnimation()),
      ])

      // Mark all stages done once we have the result
      setDoneStages(new Set(STAGES.map(s => s.id)))
      setActiveStage(null)
      setResult(apiResult)
      setUploadState('done')
    } catch (err) {
      const msg = err instanceof ApiError
        ? err.detail
        : `Unexpected error: ${(err as Error).message}`
      setErrorMsg(msg)
      setActiveStage(null)
      setUploadState('error')
    }
  }, [file, uploadState, cameraId, frameSkip, runStageAnimation])

  const handleReset = useCallback(() => {
    clearFile()
    setElapsedSec(0)
    setStartTime(null)
  }, [clearFile])

  // ── derived result stats ─────────────────────────────────────────────────

  // Build verified plates map (VERIFIED status only — not partials)
  const uniquePlatesWithConf = result
    ? (() => {
        const map = new Map<string, { maxConf: number; lowConf: boolean; count: number }>()
        result.detections.forEach(d => {
          // Only count VERIFIED plates — partial/fragment/unreadable are NOT unique plates
          const displayText = d.plate_status === 'verified' ? d.plate_number : null
          if (!displayText) return
          const existing = map.get(displayText)
          const conf = d.ocr_confidence ?? 0
          if (!existing) {
            map.set(displayText, { maxConf: conf, lowConf: d.low_confidence, count: 1 })
          } else {
            map.set(displayText, {
              maxConf: Math.max(existing.maxConf, conf),
              lowConf: existing.lowConf && d.low_confidence,
              count: existing.count + 1,
            })
          }
        })
        return Array.from(map.entries())
          .map(([plate, info]) => ({ plate, ...info }))
          .sort((a, b) => b.count - a.count)
      })()
    : []

  const vehicleTypeCounts = result
    ? result.detections.reduce<Record<string, number>>((acc, d) => {
        const t = d.vehicle_type || 'unknown'
        acc[t] = (acc[t] ?? 0) + 1
        return acc
      }, {})
    : {}

  const recentDetections = result
    ? [...result.detections]
        .filter(d => d.plate_number || d.partial_text)
        .sort((a, b) => b.frame_number - a.frame_number)
        .slice(0, 15)
    : []

  // ── render ────────────────────────────────────────────────────────────────

  return (
    <div style={{ maxWidth: 1200, margin: '0 auto' }}>
      <style>{`
        @keyframes spin { to { transform: rotate(360deg); } }
        .upload-zone-active { border-color: var(--cyan) !important; background: #e8f9fc !important; }
        .video-upload-btn:hover { opacity: .85; }
      `}</style>

      {/* ── Upload zone ───────────────────────────────────────────────────── */}
      {!file && (
        <div
          className={`panel${dragOver ? ' upload-zone-active' : ''}`}
          style={{ marginBottom: 20 }}
          onDragOver={e => { e.preventDefault(); setDragOver(true) }}
          onDragLeave={() => setDragOver(false)}
          onDrop={onDrop}
        >
          <div style={{ padding: '48px 32px', textAlign: 'center' }}>
            <div style={{
              width: 64, height: 64, borderRadius: 16,
              background: dragOver ? '#dcf4fa' : '#f0f6fb',
              display: 'grid', placeItems: 'center',
              margin: '0 auto 18px',
              border: `2px dashed ${dragOver ? 'var(--cyan)' : 'var(--border)'}`,
              transition: 'all .2s',
            }}>
              <Film size={28} color={dragOver ? 'var(--cyan)' : '#a0b4c4'} />
            </div>

            <h2 style={{ margin: '0 0 8px', fontSize: 18, letterSpacing: '-.4px' }}>
              Drop a traffic video here
            </h2>
            <p style={{ color: 'var(--muted-foreground)', fontSize: 12, margin: '0 0 22px' }}>
              Supports MP4, AVI, MOV, MKV &nbsp;·&nbsp; Maximum {MAX_SIZE_GB} GB
            </p>

            <button
              className="primary-button video-upload-btn"
              style={{ margin: '0 auto', fontSize: 13, padding: '10px 22px' }}
              onClick={() => fileInputRef.current?.click()}
            >
              <Upload size={15} />
              Choose video file
            </button>

            <input
              ref={fileInputRef}
              type="file"
              accept={ACCEPTED.join(',')}
              style={{ display: 'none' }}
              onChange={onFileInput}
            />
          </div>

          {fileError && (
            <div style={{
              margin: '0 18px 18px', padding: '10px 14px',
              background: '#1a0508', color: '#b94040',
              borderRadius: 7, fontSize: 11, display: 'flex', gap: 8, alignItems: 'center',
            }}>
              <AlertCircle size={13} style={{ flexShrink: 0 }} />
              {fileError}
            </div>
          )}
        </div>
      )}

      {/* ── File selected — preview + config ─────────────────────────────── */}
      {file && uploadState !== 'done' && (
        <div style={{ display: 'grid', gridTemplateColumns: '1.4fr 1fr', gap: 17, marginBottom: 20 }}>

          {/* Left: video preview + file info */}
          <div className="panel">
            <div className="panel-header">
              <div>
                <h2>Selected Video</h2>
                <p>Preview and file details</p>
              </div>
              {uploadState === 'idle' && (
                <button
                  onClick={clearFile}
                  style={{ border: 0, background: 'transparent', color: '#9ab', cursor: 'pointer', padding: 4 }}
                  title="Remove file"
                >
                  <X size={16} />
                </button>
              )}
            </div>

            <div style={{ padding: '14px 18px 18px' }}>
              {/* Video preview */}
              <div style={{
                borderRadius: 8, overflow: 'hidden',
                background: '#0d1c2d',
                marginBottom: 14,
                position: 'relative',
              }}>
                {previewUrl ? (
                  <video
                    src={previewUrl}
                    controls
                    style={{ width: '100%', maxHeight: 220, display: 'block' }}
                    preload="metadata"
                  />
                ) : (
                  <div style={{
                    height: 160, display: 'grid', placeItems: 'center', color: '#4a6680',
                  }}>
                    <Film size={36} />
                  </div>
                )}
              </div>

              {/* File info */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                {[
                  ['File name', file.name],
                  ['File size', formatBytes(file.size)],
                  ['Format',    '.' + file.name.split('.').pop()!.toUpperCase()],
                  ['Status',    uploadState === 'processing' ? 'Processing…' : 'Ready'],
                ].map(([label, value]) => (
                  <div key={label}>
                    <span className="kpi-label">{label}</span>
                    <strong style={{ display: 'block', fontSize: 12, marginTop: 3 }}>{value}</strong>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Right: config + pipeline stages */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 17 }}>

            {/* Config panel */}
            <div className="panel">
              <div className="panel-header">
                <div><h2>Processing Options</h2><p>Configure before running</p></div>
              </div>
              <div style={{ padding: '14px 18px 18px' }}>
                <label style={{ display: 'block', fontSize: 10, color: '#6d7f92', fontWeight: 700, marginBottom: 5, letterSpacing: '.5px' }}>
                  CAMERA ID
                </label>
                <select
                  value={cameraId}
                  onChange={e => setCameraId(e.target.value)}
                  disabled={uploadState === 'processing'}
                  style={{
                    width: '100%', padding: '8px 10px', marginBottom: 14,
                    border: '1px solid var(--border)', borderRadius: 6,
                    background: 'var(--card)', color: 'var(--foreground)',
                    fontSize: 12, cursor: 'pointer',
                  }}
                >
                  {CAMERAS.map(c => <option key={c} value={c}>{c}</option>)}
                </select>

                <label style={{ display: 'block', fontSize: 10, color: '#6d7f92', fontWeight: 700, marginBottom: 5, letterSpacing: '.5px' }}>
                  FRAME SAMPLING
                </label>
                <select
                  value={frameSkip}
                  onChange={e => setFrameSkip(Number(e.target.value))}
                  disabled={uploadState === 'processing'}
                  style={{
                    width: '100%', padding: '8px 10px',
                    border: '1px solid var(--border)', borderRadius: 6,
                    background: 'var(--card)', color: 'var(--foreground)',
                    fontSize: 12, cursor: 'pointer',
                  }}
                >
                  {FRAME_SKIP_OPTIONS.map(o => (
                    <option key={o.value} value={o.value}>{o.label}</option>
                  ))}
                </select>

                <p style={{ fontSize: 9, color: 'var(--muted-foreground)', margin: '8px 0 0' }}>
                  Lower frame skip = more detections but slower processing.
                </p>
              </div>
            </div>

            {/* Stages panel */}
            <div className="panel" style={{ flex: 1 }}>
              <div className="panel-header">
                <div>
                  <h2>Pipeline Stages</h2>
                  <p>
                    {uploadState === 'processing'
                      ? `Running… ${formatDuration(elapsedSec)}`
                      : 'Ready to process'}
                  </p>
                </div>
                {uploadState === 'processing' && (
                  <span style={{ fontSize: 9, color: 'var(--cyan)', fontWeight: 700, letterSpacing: '.5px' }}>
                    LIVE
                  </span>
                )}
              </div>
              <div style={{ padding: '4px 18px 14px' }}>

                {/* Upload progress bar */}
                {uploadState === 'processing' && uploadPct < 100 && (
                  <div style={{ margin: '10px 0 4px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 9, color: 'var(--muted-foreground)', marginBottom: 4 }}>
                      <span>Uploading to backend…</span>
                      <span>{uploadPct}%</span>
                    </div>
                    <div style={{ height: 4, background: '#1a2f44', borderRadius: 3, overflow: 'hidden' }}>
                      <div style={{
                        height: '100%', background: 'var(--cyan)', borderRadius: 3,
                        width: `${uploadPct}%`, transition: 'width .3s',
                      }} />
                    </div>
                  </div>
                )}

                {STAGES.map(stage => (
                  <StageRow
                    key={stage.id}
                    stage={stage}
                    state={
                      doneStages.has(stage.id) ? 'done'
                      : activeStage === stage.id ? 'active'
                      : 'waiting'
                    }
                  />
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── Error state ────────────────────────────────────────────────────── */}
      {uploadState === 'error' && errorMsg && (
        <div className="panel" style={{ marginBottom: 20 }}>
          <div style={{ padding: '20px 18px' }}>
            <div style={{
              display: 'flex', alignItems: 'flex-start', gap: 12,
              padding: '14px 16px', background: '#1a0508', borderRadius: 8,
            }}>
              <AlertCircle size={18} color="var(--red)" style={{ flexShrink: 0, marginTop: 1 }} />
              <div>
                <strong style={{ display: 'block', color: '#a83535', fontSize: 13, marginBottom: 4 }}>
                  Processing failed
                </strong>
                <p style={{ color: '#b94040', fontSize: 11, margin: 0 }}>{errorMsg}</p>
                <p style={{ color: '#c06060', fontSize: 10, margin: '6px 0 0' }}>
                  Make sure the backend is running at {process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'}
                </p>
              </div>
            </div>
            <div style={{ display: 'flex', gap: 10, marginTop: 14 }}>
              <button className="primary-button" onClick={handleProcess}>
                <RefreshCw size={13} /> Retry
              </button>
              <button className="date-button" onClick={handleReset}>
                <X size={13} /> Start over
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Process button ─────────────────────────────────────────────────── */}
      {file && uploadState === 'idle' && (
        <div style={{ display: 'flex', gap: 12, marginBottom: 20 }}>
          <button
            className="primary-button"
            style={{ fontSize: 14, padding: '12px 28px', flex: '0 0 auto' }}
            onClick={handleProcess}
          >
            <Play size={16} />
            Process Video
          </button>
          <button className="date-button" onClick={clearFile} style={{ padding: '12px 18px' }}>
            <X size={14} />
            Cancel
          </button>
          <p style={{ alignSelf: 'center', fontSize: 10, color: 'var(--muted-foreground)' }}>
            Calls&nbsp;<code style={{ background: 'var(--muted)', padding: '2px 5px', borderRadius: 3, fontSize: 9 }}>
              POST /process/video
            </code>
          </p>
        </div>
      )}

      {/* ── Results ────────────────────────────────────────────────────────── */}
      {result && uploadState === 'done' && (
        <>
          {/* Success banner */}
          <div style={{
            display: 'flex', alignItems: 'center', gap: 12,
            padding: '14px 18px', background: '#021a0f',
            border: '1px solid #aee8ce', borderRadius: 8, marginBottom: 20,
          }}>
            <CheckCircle2 size={20} color="var(--green)" />
            <div style={{ flex: 1 }}>
              <strong style={{ color: '#1a7a55', fontSize: 13 }}>Processing complete</strong>
              <p style={{ color: '#3a9e73', fontSize: 10, margin: '2px 0 0' }}>
                {result.source_file} processed in {formatDuration(elapsedSec)} ·
                {result.frames_processed} frames analysed (every {result.frame_skip}th frame)
                {!file && <span style={{ color: '#5a9e7a' }}> · Results restored from session — upload the video again to re-process.</span>}
              </p>
            </div>
            <button className="date-button" onClick={handleReset} style={{ fontSize: 11 }}>
              <RefreshCw size={12} /> New video
            </button>
          </div>

          {/* KPI cards */}
          <div className="kpi-grid" style={{ marginBottom: 20 }}>
            {[
              { label: 'Total detections',   value: result.total_detections,                             icon: Activity,    colour: 'cyan-bg'   },
              { label: 'Verified plates',    value: result.verified_count ?? result.unique_plates.length, icon: CreditCard,  colour: 'green-bg'  },
              { label: 'Partial reads',      value: result.partial_count  ?? result.partial_plates?.length ?? 0, icon: AlertCircle, colour: 'amber-bg'  },
              { label: 'Frames processed',   value: result.frames_processed,                             icon: Film,        colour: 'purple-bg' },
            ].map(({ label, value, icon: Icon, colour }) => (
              <article className="kpi-card" key={label}>
                <div className="kpi-top">
                  <span className={`kpi-icon ${colour}`}><Icon size={15} /></span>
                </div>
                <strong className="kpi-value">{value}</strong>
                <span className="kpi-label">{label}</span>
              </article>
            ))}
          </div>

          {/* Main results grid */}
          <div style={{ display: 'grid', gridTemplateColumns: '1.35fr 1fr', gap: 17, marginBottom: 17 }}>

            {/* Detected plates */}
            <div className="panel">
              <div className="panel-header">
                <div>
                  <h2>Detected Number Plates</h2>
                  <p>
                    {result.unique_plates.length} verified · {(result.partial_plates?.length ?? 0)} partial
                    &nbsp;— only evidence-supported results shown
                  </p>
                </div>
              </div>
              <div style={{ padding: '12px 18px 18px' }}>
                {uniquePlatesWithConf.length > 0 ? (
                  <>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 7, marginBottom: 16 }}>
                      {uniquePlatesWithConf.map(({ plate, lowConf }) => (
                        <PlateChip key={plate} plate={plate} lowConf={lowConf} />
                      ))}
                    </div>

                    <div className="table-scroll">
                      <table>
                        <thead>
                          <tr>
                            <th>PLATE NUMBER</th>
                            <th>SIGHTINGS</th>
                            <th>CONFIDENCE</th>
                            <th>STATUS</th>
                          </tr>
                        </thead>
                        <tbody>
                          {uniquePlatesWithConf.map(({ plate, count, maxConf, lowConf }) => (
                            <tr key={plate}>
                              <td>
                                <div className="plate">
                                  <div className={`plate-mark ${lowConf ? 'amber' : ''}`} />
                                  {plate}
                                </div>
                              </td>
                              <td>{count}</td>
                              <td>
                                <span className="confidence">
                                  {maxConf > 0 ? `${(maxConf * 100).toFixed(1)}%` : '—'}
                                </span>
                              </td>
                              <td>
                                <span className={`status-pill ${lowConf ? 'amber' : ''}`}>
                                  {lowConf ? 'Low confidence' : 'Verified'}
                                </span>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>

                    {/* Partial reads section */}
                    {(result.partial_plates?.length ?? 0) > 0 && (
                      <div style={{ marginTop: 16, padding: '10px 12px', background: '#1a1200', borderRadius: 7, border: '1px solid #f8d38b' }}>
                        <p style={{ fontSize: 10, fontWeight: 700, color: '#c28118', margin: '0 0 8px', letterSpacing: '.5px' }}>
                          PARTIAL READS — incomplete OCR, not verified plates
                        </p>
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                          {result.partial_plates!.map(p => (
                            <PlateChip key={p} plate={p} lowConf={true} />
                          ))}
                        </div>
                        <p style={{ fontSize: 9, color: '#c28118', margin: '8px 0 0', fontStyle: 'italic' }}>
                          These fragments were read by OCR but are too short or low-confidence to be verified plates. They are NOT counted in Verified Plates.
                        </p>
                      </div>
                    )}
                  </>
                ) : (
                  <p style={{ color: 'var(--muted-foreground)', fontSize: 11, padding: '10px 0' }}>
                    No verified plates found. Try lowering the frame skip for more coverage.
                    {(result.partial_plates?.length ?? 0) > 0 && (
                      <span> Partial reads exist — see above.</span>
                    )}
                  </p>
                )}
              </div>
            </div>

            {/* Vehicle type breakdown + processing info */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 17 }}>

              <div className="panel">
                <div className="panel-header">
                  <div><h2>Vehicle Types</h2><p>Detected in this video</p></div>
                </div>
                <div style={{ padding: '12px 18px 18px' }}>
                  {Object.entries(vehicleTypeCounts).length > 0 ? (
                    Object.entries(vehicleTypeCounts)
                      .sort((a, b) => b[1] - a[1])
                      .map(([type, count]) => (
                        <div key={type} style={{ marginBottom: 11 }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                            <span style={{ fontSize: 11, fontWeight: 600, textTransform: 'capitalize' }}>{type}</span>
                            <span style={{ fontSize: 11, color: 'var(--muted-foreground)' }}>
                              {count} ({Math.round(count / result.total_detections * 100)}%)
                            </span>
                          </div>
                          <div style={{ height: 5, background: '#1a2f44', borderRadius: 3, overflow: 'hidden' }}>
                            <div style={{
                              height: '100%', borderRadius: 3,
                              background: type === 'car' ? 'var(--cyan)' :
                                          type === 'motorcycle' ? 'var(--amber)' :
                                          type === 'bus' ? 'var(--green)' :
                                          type === 'truck' ? 'var(--purple)' : '#b0bec8',
                              width: `${Math.round(count / result.total_detections * 100)}%`,
                            }} />
                          </div>
                        </div>
                      ))
                  ) : (
                    <p style={{ color: 'var(--muted-foreground)', fontSize: 11 }}>No vehicle detections.</p>
                  )}
                </div>
              </div>

              <div className="panel">
                <div className="panel-header">
                  <div><h2>Processing Info</h2><p>Backend pipeline details</p></div>
                </div>
                <div style={{ padding: '12px 18px 18px' }}>
                  {[
                    ['Source file',     result.source_file],
                    ['Camera ID',       result.camera_id],
                    ['Total frames',    String(result.total_frames)],
                    ['Frames analysed', String(result.frames_processed)],
                    ['Frame skip',      `every ${result.frame_skip}th`],
                    ['Processing time', formatDuration(elapsedSec)],
                    ['Status',          result.status],
                  ].map(([label, value]) => (
                    <div key={label} style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', borderBottom: '1px solid #edf1f4', fontSize: 11 }}>
                      <span style={{ color: 'var(--muted-foreground)' }}>{label}</span>
                      <strong style={{ color: 'var(--foreground)', maxWidth: 160, textAlign: 'right', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{value}</strong>
                    </div>
                  ))}
                  {result.warnings.length > 0 && (
                    <div style={{ marginTop: 10, padding: '8px 10px', background: '#1a1000', borderRadius: 6 }}>
                      {result.warnings.map((w, i) => (
                        <p key={i} style={{ fontSize: 9, color: '#c28118', margin: '2px 0' }}>⚠ {w}</p>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>

          {/* Detection events timeline */}
          {recentDetections.length > 0 && (
            <div className="panel" style={{ marginBottom: 17 }}>
              <div className="panel-header">
                <div>
                  <h2>Detection Events</h2>
                  <p>Most recent plate detections from this video (showing up to 15)</p>
                </div>
              </div>
              <div style={{ padding: '0 0 4px' }}>
                <div className="table-scroll" style={{ paddingTop: 0 }}>
                  <table>
                    <thead>
                      <tr>
                        <th>PLATE NUMBER</th>
                        <th>VEHICLE TYPE</th>
                        <th>FRAME #</th>
                        <th>TIMESTAMP</th>
                        <th>CONFIDENCE</th>
                        <th>STATUS</th>
                      </tr>
                    </thead>
                    <tbody>
                      {recentDetections.map((d, i) => (
                        <tr key={i}>
                          <td>
                            <div className="plate">
                              <div className={`plate-mark ${d.low_confidence ? 'amber' : ''}`} />
                              {d.plate_number || d.partial_text || '—'}
                            </div>
                          </td>
                          <td style={{ textTransform: 'capitalize' }}>{d.vehicle_type}</td>
                          <td style={{ fontVariantNumeric: 'tabular-nums' }}>{d.frame_number}</td>
                          <td>{formatTime(d.timestamp)}</td>
                          <td>
                            <span className="confidence">
                              {d.ocr_confidence != null ? `${(d.ocr_confidence * 100).toFixed(1)}%` : '—'}
                            </span>
                          </td>
                          <td>
                            {d.plate_status === 'verified' && (
                              <span className="status-pill">Verified</span>
                            )}
                            {d.plate_status === 'partial' && (
                              <span className="status-pill amber">Partial</span>
                            )}
                            {d.plate_status === 'low_confidence' && (
                              <span className="status-pill amber">Low conf</span>
                            )}
                            {d.plate_status === 'unreadable' && (
                              <span className="status-pill red">Unreadable</span>
                            )}
                            {!d.plate_status && (
                              <span className={`status-pill ${d.low_confidence ? 'amber' : ''}`}>
                                {d.low_confidence ? 'Low confidence' : 'Verified'}
                              </span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}

          {/* Processing note from backend */}
          {result.processing_note && (
            <p style={{ fontSize: 9, color: 'var(--muted-foreground)', marginBottom: 8 }}>
              ℹ {result.processing_note}
            </p>
          )}
        </>
      )}
    </div>
  )
}
