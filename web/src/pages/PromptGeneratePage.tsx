import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import toast from 'react-hot-toast'
import { AppHeader } from '../components/AppHeader'
import { LoadingOverlay } from '../components/LoadingOverlay'
import { generateAlternatives, downloadAlternativePdf } from '../api/reports'
import type { ReportAlternative } from '../api/reports'
import { ApiError } from '../api/client'
import '../prompt.css'

const examples = [
  '3.4 x 2.3 cm meningioma in the right frontal region, CT brain plain',
  'MRI lumbar spine: L4-L5 disc bulge compressing left traversing nerve root',
  'Chest X-ray PA: right lower zone opacity with blunting of costophrenic angle',
  'USG abdomen: 12 mm gallstone, no wall thickening',
]

const labels: Record<string, string> = {
  concise: 'Concise',
  standard: 'Standard',
  detailed: 'Detailed',
}

const countWords = (r: ReportAlternative) =>
  [r.clinical_details, r.protocol, r.observations, r.impression]
    .join(' ')
    .split(/\s+/)
    .filter(Boolean).length

function Section({ title, text }: { title: string; text: string }) {
  return (
    <div className="report-section">
      <h3>{title}</h3>
      <p>{text}</p>
    </div>
  )
}

export default function PromptGeneratePage() {
  const navigate = useNavigate()
  const [prompt, setPrompt] = useState('')
  const [loading, setLoading] = useState(false)
  const [alternatives, setAlternatives] = useState<ReportAlternative[]>([])
  const [active, setActive] = useState(0)

  const current = alternatives[active]
  const words = useMemo(() => (current ? countWords(current) : 0), [current])

  const handleSubmit = async () => {
    if (!prompt.trim()) {
      toast.error('Enter the study details first')
      return
    }
    setLoading(true)
    try {
      const result = await generateAlternatives(prompt.trim())
      setAlternatives(result.reports)
      setActive(1)
      toast.success('3 draft alternatives generated')
      setTimeout(() => document.getElementById('results')?.scrollIntoView({ behavior: 'smooth' }), 100)
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Generation failed')
    } finally {
      setLoading(false)
    }
  }

  const copyReport = async (r: ReportAlternative) => {
    await navigator.clipboard.writeText(r.full_report)
    toast.success('Report copied')
  }

  const pdf = async (r: ReportAlternative) => {
    try {
      await downloadAlternativePdf(r)
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'PDF failed')
    }
  }

  return (
    <div className="min-h-screen flex flex-col">
      <AppHeader />
      {loading && <LoadingOverlay message="Drafting 3 reports" submessage="Structuring the supplied findings..." />}
      <main className="flex-1 max-w-4xl mx-auto w-full px-4 sm:px-6 py-6 sm:py-10">
        <section className="hero-card fade-in">
          <span className="eyebrow">AI-assisted drafting</span>
          <h1>Describe the study, get three report drafts</h1>
          <p>Type the modality, region and findings in your own words. You will receive concise, standard and detailed versions.</p>

          <textarea
            id="prompt-input"
            className="prompt-box"
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            onKeyDown={(e) => { if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') handleSubmit() }}
            placeholder={examples[0]}
            maxLength={8000}
          />
          <div className="chip-row">
            {examples.map((ex) => (
              <button key={ex} type="button" className="chip" onClick={() => setPrompt(ex)}>{ex}</button>
            ))}
          </div>

          <div className="hero-actions">
            <span className="hint">{prompt.length}/8000 · Ctrl+Enter to generate</span>
            <div className="flex gap-3">
              <button type="button" onClick={() => navigate('/dashboard')} className="btn btn-secondary">Cancel</button>
              <button id="generate-btn" type="button" onClick={handleSubmit} disabled={!prompt.trim() || loading} className="btn btn-primary disabled:opacity-50 disabled:cursor-not-allowed">Generate drafts</button>
            </div>
          </div>
        </section>

        {current && (
          <section id="results" className="mt-8 fade-in">
            <div className="tabs" role="tablist">
              {alternatives.map((r, i) => (
                <button
                  key={r.type}
                  role="tab"
                  aria-selected={i === active}
                  className={`tab ${i === active ? 'tab-active' : ''}`}
                  onClick={() => setActive(i)}
                >
                  {labels[r.type] ?? r.type}
                  <small>{r.word_limit} words</small>
                </button>
              ))}
            </div>

            <article className="report-card">
              <header className="report-head">
                <div>
                  <h2>{current.title}</h2>
                  <span className="word-badge">{words} words</span>
                </div>
                <div className="flex gap-2">
                  <button type="button" className="btn btn-secondary !px-4 !py-2" onClick={() => copyReport(current)}>Copy</button>
                  <button type="button" className="btn btn-primary !px-4 !py-2" onClick={() => pdf(current)}>Download PDF</button>
                </div>
              </header>
              <Section title="Clinical Details" text={current.clinical_details} />
              <Section title="Protocol" text={current.protocol} />
              <Section title="Observations" text={current.observations} />
              <Section title="Impression" text={current.impression} />
              <footer className="report-foot">
                AI-generated draft. Routine normal/negative statements are template defaults and were not supplied by you; verify every statement against the study. A qualified radiologist must approve before clinical use.
              </footer>
            </article>
          </section>
        )}
      </main>
    </div>
  )
}
