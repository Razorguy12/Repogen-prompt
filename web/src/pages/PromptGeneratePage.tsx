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
  getDraftFlags,
  getReport,
  getReportFormats,
  getReports,
  reviewDraftFlag,
  saveCustomFormat,
  updatePromptDraft,
} from '../api/reports'
import { getFinalReportForDraft } from '../api/clinical'
import { FinalizeModal } from '../components/FinalizeModal'
import { copyText } from '../lib/clipboard'
import type { PromptSession, ReportAlternative, ReportSummary, ReviewFlag, ReviewStatus } from '../types'
import { ApiError } from '../api/client'
import { ReportDocument } from '../components/ReportDocument'
import { bodyWordCount } from '../lib/reportSections'
import { FlagsPanel } from '../components/FlagsPanel'
import { ReviewPanel, type PendingCorrection } from '../components/ReviewPanel'
import { ExamChip } from '../components/ExamChip'
import { InputTips } from '../components/InputTips'
import { displayRange, parseUtc } from '../lib/reportText'
import '../prompt.css'

const examples = [
  {
    label: 'CT brain',
    prompt: 'CT brain plain. 3.4 × 2.3 cm extra-axial lesion along the right frontal convexity, suspected meningioma. Headache 2 weeks.',
  },
  {
    label: 'MRI lumbar',
    prompt: 'MRI lumbar spine: L4–L5 disc bulge compressing the left traversing nerve root. Low back pain radiating to left leg.',
  },
  {
    label: 'Chest X-ray',
    prompt: 'Chest X-ray PA: right lower zone opacity with blunting of the right costophrenic angle. Fever and cough 5 days.',
  },
  {
    label: 'USG abdomen',
    prompt: 'USG abdomen: 12 mm gallstone in the gallbladder lumen, no wall thickening, no pericholecystic fluid. Right upper quadrant pain.',
  },
]

const typeLabel: Record<string, string> = { concise: 'Concise', standard: 'Standard', detailed: 'Detailed' }

function startOfDay(d: Date) {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()
}

function dateGroupLabel(iso: string) {
  const t = startOfDay(parseUtc(iso))
  const today = startOfDay(new Date())
  const diff = Math.round((today - t) / 86_400_000)
  if (diff <= 0) return 'Today'
  if (diff === 1) return 'Yesterday'
  if (diff < 7) return 'This week'
  return parseUtc(iso).toLocaleDateString(undefined, { month: 'long', day: 'numeric', year: 'numeric' })
}

function timeLabel(iso: string) {
  return parseUtc(iso).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
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
    status: r.status,
    // Pre-v2 drafts have neither key.
    exam: params.exam ?? null,
    flags: params.flags ?? [],
    prompt_version: params.prompt_version ?? null,
  }
}

const FORMAT_KEY = 'report_format_id'

function readSavedFormatId(): string {
  try {
    const saved = localStorage.getItem(FORMAT_KEY)
    return !saved || saved === 'organwise' ? 'structured' : saved
  } catch {
    return 'structured'
  }
}

export default function PromptGeneratePage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { name, logout, isAdmin, token } = useAuth()
  const [params, setParams] = useSearchParams()
  const requestedId = Number(params.get('id') || 0)

  const [prompt, setPrompt] = useState('')
  const [formatId, setFormatId] = useState(readSavedFormatId)
  const [customFormat, setCustomFormat] = useState('')
  const [showFormat, setShowFormat] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [editing, setEditing] = useState(false)
  const [session, setSession] = useState<PromptSession | null>(null)
  const [active, setActive] = useState(1)
  const [draftText, setDraftText] = useState('')
  // Flag acknowledgements for the open draft: index -> ISO timestamp.
  const [acks, setAcks] = useState<Record<number, string>>({})
  const [finalizeOpen, setFinalizeOpen] = useState(false)
  const [reviewFlags, setReviewFlags] = useState<ReviewFlag[]>([])
  const [pendingCorrections, setPendingCorrections] = useState<PendingCorrection[]>([])
  const editorRef = useRef<HTMLTextAreaElement>(null)
  const composerRef = useRef<HTMLTextAreaElement>(null)
  const threadRef = useRef<HTMLDivElement>(null)

  const { data: reports = [] } = useQuery({
    queryKey: ['reports', token],
    queryFn: getReports,
    enabled: !!token,
  })

  const { data: formatOptions } = useQuery({
    queryKey: ['report-formats', token],
    queryFn: getReportFormats,
    enabled: !!token,
  })
  const savedCustom = !!formatOptions?.custom

  useEffect(() => {
    if (formatOptions) setCustomFormat(formatOptions.custom)
  }, [formatOptions])

  const chooseFormat = (id: string) => {
    setFormatId(id)
    try { localStorage.setItem(FORMAT_KEY, id) } catch { /* the choice just is not remembered */ }
  }

  const persistCustomFormat = async (text: string) => {
    try {
      await saveCustomFormat(text)
      queryClient.invalidateQueries({ queryKey: ['report-formats'] })
      toast.success(text.trim() ? 'Custom format saved' : 'Custom format removed')
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Could not save the format')
    }
  }

  const history = useMemo(() => {
    return reports
      .filter((r) => r.kind === 'prompt' || r.input_params?.alternatives)
      .sort((a, b) => parseUtc(b.created_at).getTime() - parseUtc(a.created_at).getTime())
  }, [reports])

  const groupedHistory = useMemo(() => {
    const groups: { label: string; items: ReportSummary[] }[] = []
    // Keep the sidebar compact so the report composer and account controls stay
    // visible without requiring the user to scroll the history panel.
    for (const item of history.slice(0, 7)) {
      const label = dateGroupLabel(item.created_at)
      const last = groups[groups.length - 1]
      if (last && last.label === label) last.items.push(item)
      else groups.push({ label, items: [item] })
    }
    return groups
  }, [history])

  const current = session?.reports[active]
  const flags = session?.flags ?? []
  // Drafts with review records use the panel; older drafts keep per-flag acknowledgement.
  const gated = reviewFlags.length > 0
  const outstanding = reviewFlags.filter((f) => f.requires_review && f.status === 'open')
  const allFlagsAcknowledged = gated ? outstanding.length === 0 : flags.every((_, i) => !!acks[i])

  useEffect(() => {
    setAcks({})
    setPendingCorrections([])
    setReviewFlags([])
    if (!session?.id) return
    let cancelled = false
    getDraftFlags(session.id)
      .then((rows) => { if (!cancelled) setReviewFlags(rows) })
      .catch(() => toast.error('Could not load the review items'))
    return () => { cancelled = true }
  }, [session?.id])

  const applyReview = async (flag: ReviewFlag, status: ReviewStatus, itemIndex: number | null) => {
    if (!session) return
    const updated = await reviewDraftFlag(session.id, flag.id, status, itemIndex)
    setReviewFlags((rows) => rows.map((r) => (r.id === updated.id ? updated : r)))
  }

  const handleReview = (flag: ReviewFlag, status: ReviewStatus, itemIndex: number | null) => {
    applyReview(flag, status, itemIndex).catch((err) =>
      toast.error(err instanceof ApiError ? err.message : 'Could not save that review'))
  }

  const handleCorrect = (flag: ReviewFlag, itemIndex: number | null, text: string) => {
    setPendingCorrections((p) => [...p, { flagId: flag.id, itemIndex }])
    setEditing(true)
    window.setTimeout(() => {
      const box = editorRef.current
      if (!box) return
      box.focus()
      const at = box.value.toLowerCase().indexOf(text.toLowerCase())
      if (at >= 0) box.setSelectionRange(at, at + text.length)
    }, 0)
  }

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
    if (session && session.status !== 'final' && reviewFlags.length > 0
      && !window.confirm('Generate again? This creates a new draft with new flags to review. Your review of this draft does not carry over.')) {
      return
    }
    setLoading(true)
    setEditing(false)
    try {
      const result = await generateAlternatives(prompt.trim(), formatId)
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
      const corrections = pendingCorrections
      for (const c of corrections) {
        const flag = reviewFlags.find((f) => f.id === c.flagId)
        if (flag) await applyReview(flag, 'corrected', c.itemIndex)
      }
      setPendingCorrections([])
      toast.success('Edits saved')
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Save failed')
    }
  }

  const copyReport = async (r: ReportAlternative) => {
    try {
      await copyText(r.full_report)
      toast.success('Copied to clipboard')
    } catch {
      toast.error('Could not copy report. Check clipboard permissions and try again.')
    }
  }

  const finalize = () => {
    if (!session || !current) return
    if (current.type !== session.selected) {
      toast.error('Select this variant first')
      return
    }
    if (gated && outstanding.length > 0) {
      document.getElementById('review-panel')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
      return
    }
    if (editing && draftText !== current.full_report) {
      toast.error('Save your edits before finalizing')
      return
    }
    setFinalizeOpen(true)
  }

  const openFinalReport = async () => {
    if (!session) return
    try {
      const { id } = await getFinalReportForDraft(session.id)
      navigate(`/final/${id}`)
    } catch {
      toast.error('This draft was marked final before patient details were introduced.')
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
          {history.length > 7 && (
            <Link to="/dashboard" className="history-library-link" onClick={() => setSidebarOpen(false)}>
              View all reports in Library
            </Link>
          )}
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
                {session.exam && (
                  <div className="mt-2"><ExamChip exam={session.exam} /></div>
                )}
                {session.report_format && (
                  <pre className="format-preview">{session.report_format}</pre>
                )}
              </article>

              <article className="bubble assistant">
                <div className="bubble-meta">repogen · three drafts</div>
                {!gated && <FlagsPanel
                  flags={flags}
                  acknowledged={acks}
                  onToggle={session.status === 'final' ? undefined : (i, checked) =>
                    setAcks((prev) => {
                      const next = { ...prev }
                      if (checked) next[i] = new Date().toISOString()
                      else delete next[i]
                      return next
                    })}
                />}
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
                      <strong>{typeLabel[r.type] ?? r.type}</strong>
                      <small>Target {displayRange(r.word_limit)} words</small>
                    </button>
                  ))}
                </div>

                {current && (
                  <div className={gated ? 'review-layout' : undefined}>
                  <div className="report-sheet">
                    <header>
                      <div>
                        <h3>{current.title}</h3>
                        <span>
                          {bodyWordCount(current.full_report, current.title, session.report_format)} words · target {displayRange(current.word_limit)} · {session.selected === current.type ? 'Selected' : 'Preview'}
                        </span>
                      </div>
                      <div className="sheet-actions">
                        <button type="button" onClick={() => setEditing((v) => !v)}>{editing ? 'Close editor' : 'Edit'}</button>
                        <button type="button" onClick={() => copyReport(current)}>Copy</button>
                        <button type="button" onClick={() => downloadAlternativeDocx(current, session.id).catch((e) => toast.error(e.message))}>Edit in Word</button>
                        <button type="button" className="accent" onClick={() => downloadAlternativePdf(current, session.id).catch((e) => toast.error(e.message))}>PDF</button>
                      </div>
                    </header>

                    {editing ? (
                      <div className="editor">
                        <textarea ref={editorRef} value={draftText} onChange={(e) => setDraftText(e.target.value)} />
                        <button type="button" className="accent" onClick={saveEdits}>Save edits to this draft</button>
                      </div>
                    ) : (
                      <div className="px-1 py-1"><ReportDocument text={current.full_report} title={current.title} reportFormat={session.report_format} /></div>
                    )}

                    <footer>
                      AI-generated draft. Not a medical record or diagnosis; it has not been reviewed or approved by a physician and requires review and sign-off by a board-certified radiologist or licensed physician before any clinical use. Choosing a tab saves that version for this timestamped record.
                      {session?.status === 'final'
                        ? (
                          <button type="button" className="text-link" onClick={openFinalReport}>
                            <span className="badge-final">Final</span> View final report
                          </button>
                        )
                        : (
                          <button
                            type="button"
                            className={`text-link ${allFlagsAcknowledged ? '' : 'opacity-50'}`}
                            onClick={finalize}
                            aria-disabled={!allFlagsAcknowledged}
                            disabled={!gated && !allFlagsAcknowledged}
                            title={allFlagsAcknowledged ? 'Finalize this report' : 'Review every flagged item before finalizing'}
                          >
                            Mark as final
                          </button>
                        )}
                      {gated && outstanding.length > 0 && session?.status !== 'final' && (
                        <span className="review-outstanding">
                          Still to review: {outstanding.map((f) => f.items.length === 1 ? f.items[0].text : f.type.replace('_', ' ')).join('; ')}
                        </span>
                      )}
                    </footer>
                  </div>
                  {gated && (
                    <ReviewPanel
                      flags={reviewFlags}
                      pending={pendingCorrections}
                      readOnly={session.status === 'final'}
                      onReview={handleReview}
                      onCorrect={handleCorrect}
                    />
                  )}
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
                <div className="format-head"><label>Report format</label></div>
                {customFormat.trim() !== '' && savedCustom && (
                  <p className="format-override">Your custom format is in use and overrides these presets.</p>
                )}
                <div className="format-options">
                  {(formatOptions?.presets ?? []).map((p) => (
                    <button
                      key={p.id}
                      type="button"
                      className="format-option"
                      aria-pressed={!savedCustom && formatId === p.id}
                      disabled={savedCustom}
                      onClick={() => chooseFormat(p.id)}
                    >
                      <strong>{p.label}</strong>
                      <small>{p.description}</small>
                    </button>
                  ))}
                </div>
                <div className="format-custom">
                  <label htmlFor="report-format">My custom format</label>
                  <textarea
                    id="report-format"
                    value={customFormat}
                    onChange={(e) => setCustomFormat(e.target.value)}
                    maxLength={formatOptions?.max_custom_chars ?? 2000}
                    placeholder="Optional house style: headings, order, numbered impression…"
                    rows={2}
                  />
                  <div className="format-custom-bar">
                    <button type="button" className="text-link" onClick={() => persistCustomFormat(customFormat)}>Save</button>
                    {savedCustom && <button type="button" className="text-link" onClick={() => persistCustomFormat('')}>Remove</button>}
                    <span>{customFormat.length}/{formatOptions?.max_custom_chars ?? 2000}</span>
                  </div>
                </div>
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
                {showFormat ? 'Hide format' : 'Report format'}
              </button>
              <span className="hint">{prompt.length}/8000 · Ctrl+Enter</span>
              <DictationButton value={prompt} onUpdate={setPrompt} compact />
              <button type="submit" className="send-btn" disabled={!prompt.trim() || loading}>
                Generate 3 drafts
              </button>
            </div>
            <InputTips />
          </div>
        </form>
      </main>
      {finalizeOpen && session && current && (
        <FinalizeModal
          draftId={session.id}
          variant={current}
          reportFormat={session.report_format}
          exam={session.exam}
          flagAcks={acks}
          onClose={() => setFinalizeOpen(false)}
          onFinalized={(report) => {
            setFinalizeOpen(false)
            queryClient.invalidateQueries({ queryKey: ['reports'] })
            navigate(`/final/${report.id}`)
          }}
        />
      )}
    </div>
  )
}
