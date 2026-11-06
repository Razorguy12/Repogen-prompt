import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { AppHeader } from '../components/AppHeader'
import { MarkdownReport } from '../components/MarkdownReport'
import { amendFinalReport, getFinalReport, recordFinalReportExport } from '../api/clinical'
import { ApiError } from '../api/client'
import { copyText } from '../lib/clipboard'
import { formatDateTime, formatStudyDate } from '../lib/reportText'
import type { FinalReport } from '../types/clinical'

export function PatientHeader({ report }: { report: Pick<FinalReport, 'patient' | 'age' | 'study_date' | 'exam'> }) {
  const obstetric = report.exam.region.trim().toLowerCase() === 'obstetric'
  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm border-b border-slate-200 pb-4 mb-4">
      <div><span className="block text-xs text-slate-500">Patient</span><strong>{report.patient.full_name}</strong></div>
      <div><span className="block text-xs text-slate-500">Patient ID</span>{report.patient.patient_identifier || '—'}</div>
      <div>
        <span className="block text-xs text-slate-500">{obstetric ? 'Age (mother) / Gender' : 'Age / Gender'}</span>
        {report.age.value} {report.age.unit} · {report.patient.gender}
      </div>
      <div><span className="block text-xs text-slate-500">Study date</span>{formatStudyDate(report.study_date)}</div>
    </div>
  )
}

function reportAsText(r: FinalReport) {
  return [
    `Patient: ${r.patient.full_name}${r.patient.patient_identifier ? ` (ID ${r.patient.patient_identifier})` : ''}`,
    `Age/Gender: ${r.age.value} ${r.age.unit} / ${r.patient.gender}`,
    `Study date: ${formatStudyDate(r.study_date)}`,
    '',
    r.final_text,
    '',
    `Finalized by ${r.doctor_name ?? 'radiologist'} on ${formatDateTime(r.finalized_at)}`,
  ].join('\n')
}

export default function FinalReportPage() {
  const { id } = useParams()
  const reportId = Number(id)
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [amending, setAmending] = useState(false)
  const [amendText, setAmendText] = useState('')
  const [saving, setSaving] = useState(false)

  const { data: report, isLoading, isError } = useQuery({
    queryKey: ['final-report', reportId],
    queryFn: () => getFinalReport(reportId),
    enabled: Number.isFinite(reportId) && reportId > 0,
  })

  if (isLoading) return <div className="min-h-screen"><AppHeader /><p className="p-8 text-slate-500">Loading…</p></div>
  if (isError || !report) {
    return (
      <div className="min-h-screen"><AppHeader />
        <div className="glass-panel max-w-md mx-auto mt-12 p-8 text-center">
          <p className="text-red-600">Final report not found.</p>
          <Link to="/dashboard" className="btn btn-primary">Back to library</Link>
        </div>
      </div>
    )
  }

  const copy = async () => {
    try {
      await copyText(reportAsText(report))
      recordFinalReportExport(report.id, 'copy').catch(() => undefined)
      toast.success('Copied to clipboard')
    } catch {
      toast.error('Could not copy. Check clipboard permissions.')
    }
  }

  const print = () => {
    recordFinalReportExport(report.id, 'print').catch(() => undefined)
    window.print()
  }

  const submitAmendment = async () => {
    if (!amendText.trim() || amendText.trim() === report.final_text.trim()) {
      toast.error('Change the text to create an amendment')
      return
    }
    if (!window.confirm('Create an amended version? The current version stays on file and is marked as amended.')) return
    setSaving(true)
    try {
      const next = await amendFinalReport(report.id, amendText)
      queryClient.invalidateQueries({ queryKey: ['final-report'] })
      toast.success('Amendment saved')
      setAmending(false)
      navigate(`/final/${next.id}`)
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Could not save amendment')
    } finally {
      setSaving(false)
    }
  }

  const superseded = !!report.superseded_by_id

  return (
    <div className="min-h-screen flex flex-col">
      <div className="print:hidden"><AppHeader /></div>
      <main className="flex-1 max-w-4xl mx-auto w-full px-4 sm:px-6 py-6 print:p-0">
        <div className="flex flex-wrap items-center justify-between gap-3 mb-4 print:hidden">
          <div className="flex items-center gap-2 flex-wrap">
            <span className={`px-2.5 py-1 rounded-full text-xs font-bold uppercase tracking-wider ${
              report.status === 'amended' ? 'bg-sky-100 text-sky-900' : 'bg-teal-100 text-teal-900'}`}>
              {report.status === 'amended' ? 'Amended version' : 'Final'}
            </span>
            {superseded && (
              <Link to={`/final/${report.superseded_by_id}`} className="px-2.5 py-1 rounded-full text-xs font-bold bg-amber-100 text-amber-900">
                Amended — see newer version
              </Link>
            )}
          </div>
          <div className="flex flex-wrap gap-2">
            <button type="button" className="btn btn-secondary py-2 px-3 text-sm" onClick={copy}>Copy</button>
            <button type="button" className="btn btn-secondary py-2 px-3 text-sm" onClick={print}>Print / PDF</button>
            {!superseded && (
              <button type="button" className="btn btn-secondary py-2 px-3 text-sm" onClick={() => { setAmendText(report.final_text); setAmending(true) }}>
                Add amendment
              </button>
            )}
            <Link to={`/compare?patient=${report.patient.id}&report=${report.id}`} className="btn btn-primary py-2 px-3 text-sm">
              Compare with another report
            </Link>
          </div>
        </div>

        <article className="glass-panel p-6 sm:p-8 print:shadow-none print:border-0 print:bg-white">
          <PatientHeader report={report} />
          <MarkdownReport text={report.final_text} />
          <p className="mt-6 pt-4 border-t border-slate-200 text-sm text-slate-600 mb-0">
            Finalized by {report.doctor_name ?? 'radiologist'} on {formatDateTime(report.finalized_at)}
            {report.status === 'amended' && ' (amendment)'}
          </p>
        </article>

        {amending && (
          <section className="glass-panel p-5 mt-6 print:hidden">
            <h2 className="text-base font-bold mt-0">Add amendment</h2>
            <p className="text-sm text-slate-600">Edit the text below. The original stays unchanged and visible.</p>
            <textarea className="form-control w-full font-mono text-sm" rows={16} value={amendText} onChange={(e) => setAmendText(e.target.value)} />
            <div className="flex gap-2 mt-3">
              <button type="button" className="btn btn-primary py-2 px-4" disabled={saving} onClick={submitAmendment}>{saving ? 'Saving…' : 'Save amendment'}</button>
              <button type="button" className="btn btn-secondary py-2 px-4" onClick={() => setAmending(false)}>Cancel</button>
            </div>
          </section>
        )}

        {(report.previous_versions?.length ?? 0) > 0 && (
          <section className="mt-6 print:hidden">
            <h3 className="text-sm font-bold uppercase tracking-wider text-slate-500">Earlier versions</h3>
            <ul className="list-none p-0 space-y-1">
              {report.previous_versions!.map((v) => (
                <li key={v.id} className="text-sm">
                  <Link to={`/final/${v.id}`} className="text-teal-800 underline">{v.status === 'amended' ? 'Amendment' : 'Original'} · {formatDateTime(v.finalized_at)}</Link>
                </li>
              ))}
            </ul>
          </section>
        )}

        {(report.comparisons?.length ?? 0) > 0 && (
          <section className="mt-6 print:hidden">
            <h3 className="text-sm font-bold uppercase tracking-wider text-slate-500">Saved comparisons</h3>
            <ul className="list-none p-0 space-y-1">
              {report.comparisons!.map((c) => (
                <li key={c.id} className="text-sm">
                  <Link to={`/comparisons/${c.id}`} className="text-teal-800 underline">
                    {formatDateTime(c.created_at)} · {c.baseline_study_date ? formatStudyDate(c.baseline_study_date) : '?'} → {c.followup_study_date ? formatStudyDate(c.followup_study_date) : '?'} ({c.interval_days} days)
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        )}
      </main>
    </div>
  )
}
