import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { getRecentFinalReports } from '../api/clinical'
import { useDebounced } from '../hooks/useDebounced'
import { formatDateTime, formatStudyDate } from '../lib/reportText'

/** All of this doctor's signed reports (latest versions), searchable by patient name or ID. */
export function FinalReportsPanel() {
  const [q, setQ] = useState('')
  const term = useDebounced(q.trim(), 300)
  const { data = [], isLoading, isError } = useQuery({
    queryKey: ['final-reports-list', term],
    queryFn: () => getRecentFinalReports(200, term),
  })

  return (
    <section>
      <input
        type="search"
        className="form-control w-full sm:max-w-sm mb-4"
        placeholder="Search by patient name or ID…"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        aria-label="Search final reports by patient name or ID"
      />
      {isError ? (
        <p className="text-red-600">Could not load final reports.</p>
      ) : isLoading ? (
        <p className="text-slate-500">Loading…</p>
      ) : data.length === 0 ? (
        <div className="glass-panel p-10 text-center text-slate-600">
          {term ? 'No final reports match that patient.' : 'No final reports yet. Mark a draft as final to file it here under the patient’s name.'}
        </div>
      ) : (
        <div className="glass-panel overflow-x-auto">
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wider text-slate-500 border-b border-slate-200">
                <th className="p-3">Patient</th>
                <th className="p-3">Patient ID</th>
                <th className="p-3">Age / Gender</th>
                <th className="p-3">Examination</th>
                <th className="p-3">Study date</th>
                <th className="p-3">Finalized</th>
                <th className="p-3"><span className="sr-only">Actions</span></th>
              </tr>
            </thead>
            <tbody>
              {data.map((r) => (
                <tr key={r.id} className="border-b border-slate-100 hover:bg-teal-50/50">
                  <td className="p-3">
                    <Link to={`/final/${r.id}`} className="font-semibold text-primary-dark no-underline hover:underline">
                      {r.patient.full_name}
                    </Link>
                    {r.status === 'amended' && <span className="ml-2 text-[11px] font-bold text-sky-800 bg-sky-100 rounded-full px-2 py-0.5">Amended</span>}
                  </td>
                  <td className="p-3 text-slate-600">{r.patient.patient_identifier || '—'}</td>
                  <td className="p-3 text-slate-600">{r.age.value} {r.age.unit} · {r.patient.gender}</td>
                  <td className="p-3">{r.exam_title}<span className="block text-xs text-slate-500">{r.exam.modality} · {r.exam.region}</span></td>
                  <td className="p-3 whitespace-nowrap">{formatStudyDate(r.study_date)}</td>
                  <td className="p-3 whitespace-nowrap text-slate-500">{formatDateTime(r.finalized_at)}</td>
                  <td className="p-3 whitespace-nowrap text-right">
                    <Link to={`/final/${r.id}`} className="text-primary font-semibold mr-3">Open</Link>
                    <Link to={`/compare?patient=${r.patient.id}&report=${r.id}`} className="text-primary font-semibold">Compare</Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
