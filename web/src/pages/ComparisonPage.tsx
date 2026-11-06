import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { AppHeader } from '../components/AppHeader'
import { FlagsPanel } from '../components/FlagsPanel'
import { ReportDocument } from '../components/ReportDocument'
import { PatientHeader } from './FinalReportPage'
import { getComparison, regenerateComparison, saveComparison } from '../api/clinical'
import { ApiError } from '../api/client'
import { copyText } from '../lib/clipboard'
import { formatDateTime, formatStudyDate } from '../lib/reportText'
import type { ChangeCategory, Comparison } from '../types/clinical'

const CATEGORY_STYLE: Record<ChangeCategory, string> = {
  NEW: 'bg-red-100 text-red-900 border-red-300',
  INCREASED: 'bg-red-100 text-red-900 border-red-300',
  DECREASED: 'bg-green-100 text-green-900 border-green-300',
  RESOLVED: 'bg-green-100 text-green-900 border-green-300',
  STABLE: 'bg-slate-100 text-slate-700 border-slate-300',
  'NOT COMPARABLE': 'bg-amber-100 text-amber-900 border-amber-300',
}

function CategoryBadge({ category }: { category: ChangeCategory }) {
  // Always shows the text label so meaning never relies on colour alone.
  return (
    <span className={`inline-block whitespace-nowrap rounded-full border px-2 py-0.5 text-[11px] font-bold tracking-wide ${CATEGORY_STYLE[category]}`}>
      {category}
    </span>
  )
}

function asText(c: Comparison, summary: string, impression: string[]) {
  const r = c.result
  return [
    r.comparison_title,
    `Baseline ${formatStudyDate(c.baseline.study_date)} → Follow-up ${formatStudyDate(c.followup.study_date)} (${c.interval_days} days)`,
    '',
    'SUMMARY',
    summary,
    '',
    'CHANGES',
    ...r.changes.map((ch) => `- [${ch.category}] ${ch.finding}: baseline: ${ch.baseline}; follow-up: ${ch.follow_up}${ch.note ? ` (${ch.note})` : ''}`),
    '',
    'IMPRESSION',
    ...impression.map((s, i) => `${i + 1}. ${s}`),
    ...(r.limitations.length ? ['', 'LIMITATIONS', ...r.limitations.map((l) => `- ${l}`)] : []),
    '',
    'AI-generated comparison draft. Verify against the original reports and images before clinical use.',
  ].join('\n')
}

export default function ComparisonPage() {
  const { id } = useParams()
  const comparisonId = Number(id)
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [summary, setSummary] = useState('')
  const [impression, setImpression] = useState<string[]>([])
  const [changesOnly, setChangesOnly] = useState(false)
  const [sideBySide, setSideBySide] = useState(false)
  const [busy, setBusy] = useState<'save' | 'regen' | null>(null)

  const { data: c, isLoading, isError } = useQuery({
    queryKey: ['comparison', comparisonId],
    queryFn: () => getComparison(comparisonId),
    enabled: comparisonId > 0,
  })

  useEffect(() => {
    if (!c) return
    setSummary(c.edited_summary ?? c.result.summary)
    setImpression(c.edited_impression ?? c.result.comparison_impression)
  }, [c])

  const changes = useMemo(
    () => (c?.result.changes ?? []).filter((ch) => !changesOnly || (ch.category !== 'STABLE' && ch.category !== 'NOT COMPARABLE')),
    [c, changesOnly],
  )

  if (isLoading) return <div className="min-h-screen"><AppHeader /><p className="p-8 text-slate-500">Loading…</p></div>
  if (isError || !c) {
    return <div className="min-h-screen"><AppHeader /><p className="p-8 text-red-600">Comparison not found. <Link to="/compare">Back</Link></p></div>
  }
  const r = c.result
  const limited = !r.examinations_comparable || r.limitations.length > 0

  const save = async () => {
    setBusy('save')
    try {
      await saveComparison(c.id, { edited_summary: summary, edited_impression: impression })
      queryClient.invalidateQueries({ queryKey: ['comparison', c.id] })
      toast.success('Comparison saved')
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Save failed')
    } finally {
      setBusy(null)
    }
  }

  const regenerate = async () => {
    setBusy('regen')
    try {
      const next = await regenerateComparison(c.id)
      toast.success('New comparison draft created; the previous one is kept')
      navigate(`/comparisons/${next.id}`)
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Regeneration failed')
    } finally {
      setBusy(null)
    }
  }

  const copy = async () => {
    try {
      await copyText(asText(c, summary, impression))
      toast.success('Copied to clipboard')
    } catch {
      toast.error('Could not copy')
    }
  }

  return (
    <div className="min-h-screen flex flex-col">
      <div className="print:hidden"><AppHeader /></div>
      <main className="flex-1 max-w-6xl mx-auto w-full px-4 sm:px-6 py-6 print:p-0">
        <div className="flex flex-wrap items-center justify-between gap-3 mb-4 print:hidden">
          <span className={`px-2.5 py-1 rounded-full text-xs font-bold uppercase tracking-wider ${c.status === 'saved' ? 'bg-teal-100 text-teal-900' : 'bg-slate-100 text-slate-700'}`}>
            {c.status === 'saved' ? 'Saved' : 'Draft'}
          </span>
          <div className="flex flex-wrap gap-2">
            <button type="button" className="btn btn-primary py-2 px-3 text-sm" disabled={!!busy} onClick={save}>{busy === 'save' ? 'Saving…' : 'Save comparison'}</button>
            <button type="button" className="btn btn-secondary py-2 px-3 text-sm" onClick={copy}>Copy</button>
            <button type="button" className="btn btn-secondary py-2 px-3 text-sm" onClick={() => window.print()}>Print / PDF</button>
            <button type="button" className="btn btn-secondary py-2 px-3 text-sm" disabled={!!busy} onClick={regenerate}>{busy === 'regen' ? 'Regenerating…' : 'Regenerate'}</button>
          </div>
        </div>

        <article className="glass-panel p-5 sm:p-8 print:shadow-none print:border-0 print:bg-white">
          <PatientHeader report={{ ...c.followup, patient: c.patient }} />
          <h1 className="text-xl font-bold mt-0 mb-1">{r.comparison_title}</h1>
          <p className="text-sm text-slate-600 mt-0">
            <Link to={`/final/${c.baseline.id}`} className="text-teal-800">Baseline {c.baseline.exam.modality} {c.baseline.exam.region} · {formatStudyDate(c.baseline.study_date)}</Link>
            {' → '}
            <Link to={`/final/${c.followup.id}`} className="text-teal-800">Follow-up {c.followup.exam.modality} {c.followup.exam.region} · {formatStudyDate(c.followup.study_date)}</Link>
            {' '}({c.interval_days} days)
          </p>

          {limited && (
            <div role="alert" className="rounded-xl border border-amber-300 bg-amber-50 p-4 my-4 text-amber-950 text-sm">
              <strong>{r.examinations_comparable ? 'Comparison limitations' : 'Examinations are not directly comparable'}</strong>
              {r.limitations.length > 0 && <ul className="mb-0 mt-1 pl-5">{r.limitations.map((l, i) => <li key={i}>{l}</li>)}</ul>}
            </div>
          )}

          <FlagsPanel flags={r.flags} />

          <h2 className="text-sm font-bold uppercase tracking-wider text-slate-500 mt-6">Summary</h2>
          <textarea className="form-control w-full print:hidden" rows={5} value={summary} onChange={(e) => setSummary(e.target.value)} />
          <p className="hidden print:block whitespace-pre-wrap">{summary}</p>

          <div className="flex items-center justify-between mt-6">
            <h2 className="text-sm font-bold uppercase tracking-wider text-slate-500 m-0">Changes</h2>
            <label className="text-sm flex items-center gap-2 cursor-pointer print:hidden">
              <input type="checkbox" checked={changesOnly} onChange={(e) => setChangesOnly(e.target.checked)} /> Changes only
            </label>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm border-collapse mt-2">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wider text-slate-500 border-b border-slate-200">
                  <th className="p-2">Finding</th><th className="p-2">Category</th><th className="p-2">Baseline</th><th className="p-2">Follow-up</th><th className="p-2">Note</th>
                </tr>
              </thead>
              <tbody>
                {changes.map((ch, i) => (
                  <tr key={i} className="border-b border-slate-100 align-top">
                    <td className="p-2 font-semibold">{ch.finding}</td>
                    <td className="p-2"><CategoryBadge category={ch.category} /></td>
                    <td className="p-2">{ch.baseline}</td>
                    <td className="p-2">{ch.follow_up}</td>
                    <td className="p-2 text-slate-600">{ch.note}</td>
                  </tr>
                ))}
                {changes.length === 0 && <tr><td colSpan={5} className="p-3 text-slate-500">No findings to show.</td></tr>}
              </tbody>
            </table>
          </div>

          <h2 className="text-sm font-bold uppercase tracking-wider text-slate-500 mt-6">Comparison impression</h2>
          <ol className="pl-5 space-y-2">
            {impression.map((line, i) => (
              <li key={i}>
                <div className="flex gap-2 print:hidden">
                  <input className="form-control flex-1" value={line}
                    onChange={(e) => setImpression((prev) => prev.map((x, j) => (j === i ? e.target.value : x)))} />
                  <button type="button" className="btn btn-secondary py-1 px-2 text-xs" aria-label="Remove line"
                    onClick={() => setImpression((prev) => prev.filter((_, j) => j !== i))}>Remove</button>
                </div>
                <span className="hidden print:inline">{line}</span>
              </li>
            ))}
          </ol>
          <button type="button" className="text-sm text-teal-800 underline bg-transparent border-0 cursor-pointer print:hidden"
            onClick={() => setImpression((prev) => [...prev, ''])}>+ Add line</button>

          <div className="mt-6 print:hidden">
            <label className="text-sm flex items-center gap-2 cursor-pointer">
              <input type="checkbox" checked={sideBySide} onChange={(e) => setSideBySide(e.target.checked)} /> Show both full reports side by side
            </label>
            {sideBySide && (
              <div className="grid md:grid-cols-2 gap-4 mt-3">
                {[{ label: 'Baseline', fr: c.baseline }, { label: 'Follow-up', fr: c.followup }].map(({ label, fr }) => (
                  <div key={label} className="rounded-xl border border-slate-200 p-4">
                    <div className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-2">
                      {label} · {formatStudyDate(fr.study_date)}
                    </div>
                    <ReportDocument text={fr.final_text} title={fr.exam_title} reportFormat={fr.report_format} showTitle />
                  </div>
                ))}
              </div>
            )}
          </div>

          <p className="mt-8 pt-4 border-t border-slate-200 text-xs text-slate-500 mb-0">
            AI-generated comparison draft. Verify against the original reports and images before clinical use.
            {' '}Generated {formatDateTime(c.created_at)}.
          </p>
        </article>
      </main>
    </div>
  )
}
