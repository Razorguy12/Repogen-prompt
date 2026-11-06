import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { AppHeader } from '../components/AppHeader'
import { PatientSearch } from '../components/PatientSearch'
import { generateComparison, getPatient, getPatientComparisons, getPatientFinalReports } from '../api/clinical'
import { ApiError } from '../api/client'
import { formatDateTime, formatStudyDate } from '../lib/reportText'
import { orderPair, intervalDays, sameExam, filterReports, type ReportFilters } from '../lib/compare'
import type { FinalReportSummary, Patient } from '../types/clinical'

function Chip({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`px-3 py-1 rounded-full text-xs font-semibold border cursor-pointer ${
        active ? 'bg-primary text-white border-primary' : 'bg-white text-slate-700 border-slate-300 hover:bg-slate-50'
      }`}
    >
      {children}
    </button>
  )
}

const examLabel = (r: FinalReportSummary) => `${r.exam.modality} ${r.exam.region}`
const NO_REPORTS: FinalReportSummary[] = []

export default function ComparePage() {
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const patientId = Number(params.get('patient') || 0)
  const preselected = Number(params.get('report') || 0)

  const [selected, setSelected] = useState<number[]>([])
  const [filters, setFilters] = useState<ReportFilters>({ modalities: [], regions: [], from: '', to: '', sameExamOnly: true })
  const [baselineChoice, setBaselineChoice] = useState<number | null>(null)
  const [busy, setBusy] = useState(false)

  const { data: patient } = useQuery({
    queryKey: ['patient', patientId],
    queryFn: () => getPatient(patientId),
    enabled: patientId > 0,
  })
  const { data: reports = NO_REPORTS, isLoading } = useQuery({
    queryKey: ['patient-final-reports', patientId],
    queryFn: () => getPatientFinalReports(patientId),
    enabled: patientId > 0,
  })

  const { data: history = [] } = useQuery({
    queryKey: ['patient-comparisons', patientId],
    queryFn: () => getPatientComparisons(patientId),
    enabled: patientId > 0,
  })

  useEffect(() => {
    setSelected(preselected && reports.some((r) => r.id === preselected) ? [preselected] : [])
    setBaselineChoice(null)
  }, [patientId, preselected, reports])

  const choosePatient = (p: Patient) => setParams({ patient: String(p.id) })

  const modalityOptions = useMemo(() => [...new Set(reports.map((r) => r.exam.modality))].sort(), [reports])
  const regionOptions = useMemo(() => [...new Set(reports.map((r) => r.exam.region))].sort(), [reports])
  const selectedReports = selected.map((id) => reports.find((r) => r.id === id)).filter(Boolean) as FinalReportSummary[]
  const anchor = selectedReports.length === 1 ? selectedReports[0] : null
  const visible = useMemo(() => filterReports(reports, filters, anchor, selected), [reports, filters, anchor, selected])

  const toggle = (id: number) => {
    setBaselineChoice(null)
    setSelected((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : prev.length >= 2 ? prev : [...prev, id]))
  }

  const toggleIn = (key: 'modalities' | 'regions', value: string) =>
    setFilters((f) => ({ ...f, [key]: f[key].includes(value) ? f[key].filter((v) => v !== value) : [...f[key], value] }))

  const pair = selectedReports.length === 2 ? orderPair(selectedReports[0], selectedReports[1], baselineChoice) : null
  const sameDate = pair && pair.baseline.study_date === pair.followup.study_date
  const differentExam = pair && !sameExam(pair.baseline, pair.followup)
  const canGenerate = !!pair && (!sameDate || baselineChoice !== null) && !busy

  const generate = async () => {
    if (!pair) return
    setBusy(true)
    try {
      const comparison = await generateComparison(pair.baseline.id, pair.followup.id)
      navigate(`/comparisons/${comparison.id}`)
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Comparison failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="min-h-screen flex flex-col">
      <AppHeader />
      <main className="flex-1 max-w-6xl mx-auto w-full px-4 sm:px-6 py-6 pb-32">
        <h1 className="text-2xl sm:text-3xl font-bold text-primary-dark mt-0">Compare reports</h1>

        <section className="glass-panel p-4 sm:p-5 mb-6">
          <h2 className="text-sm font-bold uppercase tracking-wider text-slate-500 mt-0">1 · Find the patient</h2>
          {patient ? (
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <strong className="text-lg">{patient.full_name}</strong>
                <span className="text-sm text-slate-500">
                  {' '}· {patient.patient_identifier ? `ID ${patient.patient_identifier}` : 'No ID'} · {patient.gender} · {patient.report_count} final report{patient.report_count === 1 ? '' : 's'}
                  {patient.latest_study_date ? ` · latest ${formatStudyDate(patient.latest_study_date)}` : ''}
                </span>
              </div>
              <button type="button" className="btn btn-secondary py-1.5 px-3 text-sm" onClick={() => setParams({})}>Change patient</button>
            </div>
          ) : (
            <PatientSearch onSelect={choosePatient} placeholder="Search by patient name or ID" autoFocus />
          )}
        </section>

        {patient && (
          <section className="glass-panel p-4 sm:p-5">
            <h2 className="text-sm font-bold uppercase tracking-wider text-slate-500 mt-0">2 · Pick two reports</h2>

            <div className="flex flex-wrap gap-x-6 gap-y-3 mb-4 text-sm">
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="text-xs font-bold text-slate-500 mr-1">Modality</span>
                {modalityOptions.map((m) => <Chip key={m} active={filters.modalities.includes(m)} onClick={() => toggleIn('modalities', m)}>{m}</Chip>)}
              </div>
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="text-xs font-bold text-slate-500 mr-1">Region</span>
                {regionOptions.map((r) => <Chip key={r} active={filters.regions.includes(r)} onClick={() => toggleIn('regions', r)}>{r}</Chip>)}
              </div>
              <div className="flex items-center gap-1.5">
                <span className="text-xs font-bold text-slate-500">From</span>
                <input type="date" className="form-control py-1" value={filters.from} onChange={(e) => setFilters((f) => ({ ...f, from: e.target.value }))} />
                <span className="text-xs font-bold text-slate-500">To</span>
                <input type="date" className="form-control py-1" value={filters.to} onChange={(e) => setFilters((f) => ({ ...f, to: e.target.value }))} />
              </div>
              <label className="flex items-center gap-2 cursor-pointer">
                <input type="checkbox" checked={filters.sameExamOnly} onChange={(e) => setFilters((f) => ({ ...f, sameExamOnly: e.target.checked }))} />
                Same exam only
              </label>
            </div>

            {isLoading ? <p className="text-slate-500">Loading reports…</p> : reports.length === 0 ? (
              <p className="text-slate-500">This patient has no final reports yet.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm border-collapse">
                  <thead>
                    <tr className="text-left text-xs uppercase tracking-wider text-slate-500 border-b border-slate-200">
                      <th className="p-2 w-8"><span className="sr-only">Select</span></th>
                      <th className="p-2">Study date</th><th className="p-2">Modality</th><th className="p-2">Region</th>
                      <th className="p-2">Laterality</th><th className="p-2">Exam</th><th className="p-2">Finalized by</th><th className="p-2">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {visible.map((r) => {
                      const checked = selected.includes(r.id)
                      const disabled = !checked && selected.length >= 2
                      return (
                        <tr key={r.id} className={`border-b border-slate-100 ${checked ? 'bg-teal-50' : ''} ${disabled ? 'opacity-50' : ''}`}>
                          <td className="p-2">
                            <input type="checkbox" checked={checked} disabled={disabled} onChange={() => toggle(r.id)}
                              aria-label={`Select ${r.exam_title} ${formatStudyDate(r.study_date)}`} />
                          </td>
                          <td className="p-2 whitespace-nowrap">{formatStudyDate(r.study_date)}</td>
                          <td className="p-2">{r.exam.modality}</td>
                          <td className="p-2">{r.exam.region}</td>
                          <td className="p-2">{r.exam.laterality}</td>
                          <td className="p-2">{r.exam_title}</td>
                          <td className="p-2">{r.doctor_name}</td>
                          <td className="p-2">{r.status === 'amended' ? 'Amended' : 'Final'}</td>
                        </tr>
                      )
                    })}
                    {visible.length === 0 && (
                      <tr><td colSpan={8} className="p-4 text-center text-slate-500">No reports match these filters.</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        )}

        {patient && history.length > 0 && (
          <section className="glass-panel p-4 sm:p-5 mt-6">
            <h2 className="text-sm font-bold uppercase tracking-wider text-slate-500 mt-0">Saved comparisons</h2>
            <ul className="list-none p-0 m-0 space-y-1">
              {history.map((h) => (
                <li key={h.id} className="text-sm">
                  <Link to={`/comparisons/${h.id}`} className="text-teal-800 underline">
                    {formatDateTime(h.created_at)} · {h.baseline_study_date ? formatStudyDate(h.baseline_study_date) : '?'} → {h.followup_study_date ? formatStudyDate(h.followup_study_date) : '?'} ({h.interval_days} days)
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        )}
      </main>

      {pair && (
        <div className="fixed bottom-0 inset-x-0 z-40 bg-white/95 backdrop-blur border-t border-slate-200 shadow-[0_-6px_24px_rgba(0,0,0,0.08)]">
          <div className="max-w-6xl mx-auto px-4 sm:px-6 py-3 flex flex-wrap items-center justify-between gap-3">
            <div className="text-sm">
              <div>
                <strong>Baseline:</strong> {examLabel(pair.baseline)} · {formatStudyDate(pair.baseline.study_date)}
                {' → '}
                <strong>Follow-up:</strong> {examLabel(pair.followup)} · {formatStudyDate(pair.followup.study_date)}
                {' · '}Interval {intervalDays(pair.baseline, pair.followup)} days
              </div>
              {differentExam && (
                <div className="mt-1 text-amber-800 font-semibold">⚠ Different examinations — comparison will be limited.</div>
              )}
              {sameDate && (
                <div className="mt-1 text-amber-800">
                  ⚠ Both studies share a date. Which is the baseline?{' '}
                  {selectedReports.map((r) => (
                    <label key={r.id} className="ml-2 inline-flex items-center gap-1 cursor-pointer">
                      <input type="radio" name="baseline" checked={baselineChoice === r.id} onChange={() => setBaselineChoice(r.id)} />
                      {r.exam_title} (#{r.id})
                    </label>
                  ))}
                </div>
              )}
            </div>
            <button type="button" className="btn btn-primary py-2 px-4 disabled:opacity-50" disabled={!canGenerate} onClick={generate}>
              {busy ? 'Generating…' : 'Generate comparison'}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
