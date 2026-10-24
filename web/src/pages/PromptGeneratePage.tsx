import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { DictationButton } from '../components/DictationButton'
import { useAuth } from '../context/AuthContext'
import {
  downloadAlternativeDocx,
  downloadAlternativePdf,
  generateAlternatives,
  getReport,
  getReports,
  updatePromptDraft,
  updateReportStatus,
} from '../api/reports'
import type { PromptSession, ReportAlternative, ReportSummary } from '../types'
import { ApiError } from '../api/client'
import '../prompt.css'

const examples = [
  {
    label: 'CT brain',
    prompt: 'CT brain plain. 3.4 × 2.3 cm extra-axial lesion along the right frontal convexity, suspected meningioma. Headache 2 weeks.',
    format: 'Title\nClinical Details\nProtocol\nObservations\nImpression',
  },
  {
    label: 'MRI lumbar',
    prompt: 'MRI lumbar spine: L4–L5 disc bulge compressing the left traversing nerve root. Low back pain radiating to left leg.',
    format: 'EXAMINATION\nTECHNIQUE\nFINDINGS (by level)\nIMPRESSION (numbered)',
  },
  {
    label: 'Chest X-ray',
    prompt: 'Chest X-ray PA: right lower zone opacity with blunting of the right costophrenic angle. Fever and cough 5 days.',
    format: 'Study\nClinical history\nFindings\nImpression',
  },
  {
    label: 'USG abdomen',
    prompt: 'USG abdomen: 12 mm gallstone in the gallbladder lumen, no wall thickening, no pericholecystic fluid. Right upper quadrant pain.',
    format: 'Organ-wise: Liver, Gallbladder, Pancreas, Spleen, Kidneys, Impression',
  },
]

const formatPresets = [
  { label: 'Classic', text: 'Title\nClinical Details\nProtocol\nObservations\nImpression' },
  { label: 'Numbered impression', text: 'Examination\nTechnique\nFindings\nImpression (numbered list)\nRecommendation' },
  { label: 'Organ-wise', text: 'Clinical indication\nTechnique\nFindings by organ / region\nImpression' },
]

const typeCopy: Record<string, { label: string; hint: string }> = {
  concise: { label: 'Concise', hint: '80–120 words' },
  standard: { label: 'Standard', hint: '150–200 words' },
  detailed: { label: 'Detailed', hint: '200–280 words' },
}

const countWords = (r: ReportAlternative) =>
  [r.clinical_details, r.protocol, r.observations, r.impression]
    .join(' ')
    .split(/\s+/)
    .filter(Boolean).length

function startOfDay(d: Date) {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()
}

function dateGroupLabel(iso: string) {
  const t = startOfDay(new Date(iso))
  const today = startOfDay(new Date())
  const diff = Math.round((today - t) / 86_400_000)
  if (diff <= 0) return 'Today'
  if (diff === 1) return 'Yesterday'
  if (diff < 7) return 'This week'
  return new Date(iso).toLocaleDateString(undefined, { month: 'long', day: 'numeric', year: 'numeric' })
}

function timeLabel(iso: string) {
  return new Date(iso).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
}

function sessionFromSummary(r: ReportSummary): PromptSession | null {
  const params = r.input_params || {}
  const alternatives = params.alternatives
  if (!alternatives?.length) return null
  return {
    id: r.id,
    created_at: r.created_at,
    selected: params.selected || 'standard',
    reports: alternatives,
    prompt: params.prompt || '',
    report_format: params.report_format || '',
  }
}

export default function PromptGeneratePage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { name, logout, isAdmin, token } = useAuth()
  const [params, setParams] = useSearchParams()
  const requestedId = Number(params.get('id') || 0)

  const [prompt, setPrompt] = useState('')
  const [reportFormat, setReportFormat] = useState('')
  const [showFormat, setShowFormat] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [editing, setEditing] = useState(false)
  const [session, setSession] = useState<PromptSession | null>(null)
  const [active, setActive] = useState(1)
  const [draftText, setDraftText] = useState('')
  const composerRef = useRef<HTMLTextAreaElement>(null)
  const threadRef = useRef<HTMLDivElement>(null)

  const { data: reports = [] } = useQuery({
    queryKey: ['reports', token],
    queryFn: getReports,
    enabled: !!token,
  })

  const history = useMemo(() => {
    return reports
      .filter((r) => r.kind === 'prompt' || r.input_params?.alternatives)
      .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
  }, [reports])

  const groupedHistory = useMemo(() => {
    const groups: { label: string; items: ReportSummary[] }[] = []
    for (const item of history) {
      const label = dateGroupLabel(item.created_at)
      const last = groups[groups.length - 1]
      if (last && last.label === label) last.items.push(item)
      else groups.push({ label, items: [item] })
    }
    return groups
  }, [history])

  const current = session?.reports[active]

  useEffect(() => {
    if (current) setDraftText(current.full_report)
  }, [current, session?.id])

  useEffect(() => {
    threadRef.current?.scrollTo({ top: threadRef.current.scrollHeight, behavior: 'smooth' })
  }, [session, loading])

  useEffect(() => {
    if (!requestedId || !token) return
    let cancelled = false
    getReport(requestedId)
      .then((summary) => {
        if (cancelled) return
        const loaded = sessionFromSummary(summary)
        if (!loaded) {
          toast.error('This record is not a prompt draft')
          return
        }
        setSession(loaded)
        setPrompt(loaded.prompt)
        setReportFormat(loaded.report_format || '')
        const idx = loaded.reports.findIndex((r) => r.type === loaded.selected)
        setActive(idx >= 0 ? idx : 1)
        setEditing(false)
      })
      .catch(() => toast.error('Could not open that draft'))
    return () => {
      cancelled = true
    }
  }, [requestedId, token])

  const applySession = (next: PromptSession, replaceUrl = true) => {
    setSession(next)
    const idx = next.reports.findIndex((r) => r.type === next.selected)
    setActive(idx >= 0 ? idx : 1)
    setEditing(false)
    if (replaceUrl) setParams({ id: String(next.id) }, { replace: true })
    queryClient.invalidateQueries({ queryKey: ['reports'] })
  }

  const startNew = () => {
    setSession(null)
    setPrompt('')
    setReportFormat('')
    setEditing(false)
    setActive(1)
    setParams({}, { replace: true })
    setSidebarOpen(false)
    composerRef.current?.focus()
  }

  const handleSubmit = async () => {
    if (!prompt.trim()) {
      toast.error('Describe the study and findings first')
      return
    }
    setLoading(true)
    setEditing(false)
    try {
      const result = await generateAlternatives(prompt.trim(), reportFormat.trim())
      applySession(result)
      toast.success('Three drafts are ready — pick one')
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Generation failed')
    } finally {
      setLoading(false)
    }
  }

  const selectVariant = async (index: number) => {
    if (!session) return
    setActive(index)
    setEditing(false)
    const chosen = session.reports[index]
    try {
      const next = await updatePromptDraft(session.id, { selected: chosen.type })
      setSession(next)
      queryClient.invalidateQueries({ queryKey: ['reports'] })
    } catch {
      toast.error('Could not save that choice')
    }
  }

  const saveEdits = async () => {
    if (!session || !current) return
    const updated: ReportAlternative = { ...current, full_report: draftText }
    try {
      const next = await updatePromptDraft(session.id, { selected: current.type, report: updated })
      applySession(next, false)
      toast.success('Edits saved')
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Save failed')
    }
  }

  const copyReport = async (r: ReportAlternative) => {
    try {
      if (navigator.clipboard?.writeText && window.isSecureContext) {
        await navigator.clipboard.writeText(r.full_report)
      } else {
        const copyArea = document.createElement('textarea')
        copyArea.value = r.full_report
        copyArea.setAttribute('readonly', '')
        copyArea.style.position = 'fixed'
        copyArea.style.opacity = '0'
        document.body.appendChild(copyArea)
        copyArea.select()
        const copied = document.execCommand('copy')
        copyArea.remove()
        if (!copied) throw new Error('Clipboard access is unavailable')
      }
      toast.success('Copied to clipboard')
    } catch {
      toast.error('Could not copy report. Check clipboard permissions and try again.')
    }
  }

  const finalize = async () => {
    if (!session) return
    try {
      await updateReportStatus(session.id, 'final')
      toast.success('Marked as final')
      queryClient.invalidateQueries({ queryKey: ['reports'] })
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Could not finalize')
    }
  }

  return (
    <div className="studio">
      <aside className={`studio-sidebar ${sidebarOpen ? 'is-open' : ''}`}>
        <div className="sidebar-brand">
          <Link to="/dashboard" className="brand-mark">repogen</Link>
          <button type="button" className="ghost-btn" onClick={startNew}>New chat</button>
        </div>
        <div className="sidebar-scroll">
          {groupedHistory.length === 0 && (
            <p className="sidebar-empty">Reports you generate are filed here by date and time.</p>
          )}
          {groupedHistory.map((group) => (
            <section key={group.label} className="history-group">
              <h2>{group.label}</h2>
              {group.items.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  className={`history-item ${session?.id === item.id ? 'is-active' : ''}`}
                  onClick={() => {
                    setParams({ id: String(item.id) })
                    setSidebarOpen(false)
                  }}
                >
                  <span className="history-title">{item.patient_name || 'Untitled draft'}</span>
                  <span className="history-meta">
                    {timeLabel(item.created_at)} · {item.modality}
                  </span>
                </button>
              ))}
            </section>
          ))}
        </div>
        <div className="sidebar-user">
          <div>
            <strong>{name}</strong>
            <span>Signed in</span>
          </div>
          <div className="sidebar-user-actions">
            {isAdmin && <Link to="/admin">Admin</Link>}
            <button type="button" onClick={() => { logout(); navigate('/login') }}>Log out</button>
          </div>
        </div>
      </aside>

      {sidebarOpen && <button type="button" className="sidebar-backdrop" onClick={() => setSidebarOpen(false)} aria-label="Close history" />}

      <main className="studio-main">
        <header className="studio-top">
          <button type="button" className="icon-btn md-only" onClick={() => setSidebarOpen(true)} aria-label="Open history">
            <span />
            <span />
            <span />
          </button>
          <div>
            <p className="kicker">Radiology workspace</p>
            <h1>{session ? session.reports[active]?.title || 'Draft reports' : 'New report'}</h1>
          </div>
          <Link to="/dashboard" className="ghost-btn">Library</Link>
        </header>

        <div className="studio-thread" ref={threadRef}>
          {!session && !loading && (
            <section className="empty-hero">
              <p className="eyebrow">Doctor-in-the-loop drafting</p>
              <h2>What should this report say?</h2>
              <p>
                Dictate or type the findings, optionally lock a house format, and repogen will return three drafts
                you can choose from, edit in Word, and keep on file by date.
              </p>
              <div className="example-grid">
                {examples.map((ex) => (
                  <button
                    key={ex.label}
                    type="button"
                    className="example-card"
                    onClick={() => {
                      setPrompt(ex.prompt)
                      setReportFormat(ex.format)
                      composerRef.current?.focus()
                    }}
                  >
                    <strong>{ex.label}</strong>
                    <span>{ex.prompt}</span>
                  </button>
                ))}
              </div>
            </section>
          )}

          {session && (
            <div className="thread">
              <article className="bubble user">
                <div className="bubble-meta">You · {timeLabel(session.created_at)}</div>
                <p>{session.prompt}</p>
                {session.report_format && (
                  <pre className="format-preview">{session.report_format}</pre>
                )}
              </article>

              <article className="bubble assistant">
                <div className="bubble-meta">repogen · three drafts</div>
                <div className="variant-tabs" role="tablist">
                  {session.reports.map((r, i) => (
                    <button
                      key={r.type}
                      type="button"
                      role="tab"
                      aria-selected={i === active}
                      className={`variant-tab ${i === active ? 'is-active' : ''} ${session.selected === r.type ? 'is-chosen' : ''}`}
                      onClick={() => selectVariant(i)}
                    >
                      <strong>{typeCopy[r.type]?.label ?? r.type}</strong>
                      <small>{typeCopy[r.type]?.hint ?? r.word_limit}</small>
                    </button>
                  ))}
                </div>

                {current && (
                  <div className="report-sheet">
                    <header>
                      <div>
                        <h3>{current.title}</h3>
                        <span>{countWords(current)} words · {session.selected === current.type ? 'Selected' : 'Preview'}</span>
                      </div>
                      <div className="sheet-actions">
                        <button type="button" onClick={() => setEditing((v) => !v)}>{editing ? 'Close editor' : 'Edit'}</button>
                        <button type="button" onClick={() => copyReport(current)}>Copy</button>
                        <button type="button" onClick={() => downloadAlternativeDocx(current).catch((e) => toast.error(e.message))}>Edit in Word</button>
                        <button type="button" className="accent" onClick={() => downloadAlternativePdf(current).catch((e) => toast.error(e.message))}>PDF</button>
                      </div>
                    </header>

                    {editing ? (
                      <div className="editor">
                        <textarea value={draftText} onChange={(e) => setDraftText(e.target.value)} />
                        <button type="button" className="accent" onClick={saveEdits}>Save edits to this draft</button>
                      </div>
                    ) : (
                      <div className="report-body">
                        <section>
                          <h4>Clinical Details</h4>
                          <p>{current.clinical_details}</p>
                        </section>
                        <section>
                          <h4>Protocol</h4>
                          <p>{current.protocol}</p>
                        </section>
                        <section>
                          <h4>Observations</h4>
                          <p>{current.observations}</p>
                        </section>
                        <section className="impression">
                          <h4>Impression</h4>
                          <p>{current.impression}</p>
                        </section>
                      </div>
                    )}

                    <footer>
                      AI-generated draft. Verify every statement against the study. Choosing a tab saves that version for this timestamped record.
                      <button type="button" className="text-link" onClick={finalize}>Mark final</button>
                    </footer>
                  </div>
                )}
              </article>
            </div>
          )}

          {loading && (
            <div className="thinking">
              <span className="pulse" />
              Drafting concise, standard, and detailed reports…
            </div>
          )}
        </div>

        <form
          className="composer"
          onSubmit={(e) => {
            e.preventDefault()
            handleSubmit()
          }}
        >
          <div className="composer-box">
            {showFormat && (
              <div className="format-field">
                <div className="format-head">
                  <label htmlFor="report-format">Report format</label>
                  <div className="preset-row">
                    {formatPresets.map((p) => (
                      <button key={p.label} type="button" onClick={() => setReportFormat(p.text)}>{p.label}</button>
                    ))}
                  </div>
                </div>
                <textarea
                  id="report-format"
                  value={reportFormat}
                  onChange={(e) => setReportFormat(e.target.value)}
                  placeholder="Optional house style — headings, order, numbered impression…"
                  rows={2}
                />
              </div>
            )}
            <textarea
              ref={composerRef}
              id="prompt-input"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              onKeyDown={(e) => {
                if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') handleSubmit()
              }}
              placeholder="Dictate or type the study, clinical context, and findings…"
              maxLength={8000}
              rows={3}
            />
            <div className="composer-bar">
              <button type="button" className="text-link" onClick={() => setShowFormat((v) => !v)}>
                {showFormat ? 'Hide format' : 'Add format'}
              </button>
              <span className="hint">{prompt.length}/8000 · Ctrl+Enter</span>
              <DictationButton value={prompt} onUpdate={setPrompt} compact />
              <button type="submit" className="send-btn" disabled={!prompt.trim() || loading}>
                Generate 3 drafts
              </button>
            </div>
          </div>
        </form>
      </main>
    </div>
  )
}
