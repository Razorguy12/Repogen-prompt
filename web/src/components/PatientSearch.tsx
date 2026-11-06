import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { searchPatients } from '../api/clinical'
import { useDebounced } from '../hooks/useDebounced'
import { formatStudyDate } from '../lib/reportText'
import type { Patient } from '../types/clinical'

/** Debounced (300 ms) search by partial name or patient ID, scoped server-side to this doctor. */
export function PatientSearch({
  onSelect,
  placeholder = 'Search existing patient by name or ID',
  autoFocus,
}: {
  onSelect: (p: Patient) => void
  placeholder?: string
  autoFocus?: boolean
}) {
  const [q, setQ] = useState('')
  const term = useDebounced(q.trim(), 300)
  const { data = [], isFetching } = useQuery({
    queryKey: ['patient-search', term],
    queryFn: () => searchPatients(term),
    enabled: term.length >= 2,
    staleTime: 10_000,
  })

  return (
    <div>
      <input
        type="search"
        className="form-control w-full"
        placeholder={placeholder}
        value={q}
        autoFocus={autoFocus}
        onChange={(e) => setQ(e.target.value)}
        aria-label={placeholder}
      />
      {term.length >= 2 && (
        <ul className="mt-2 max-h-64 overflow-auto rounded-lg border border-slate-200 bg-white divide-y divide-slate-100 list-none p-0 m-0">
          {isFetching && data.length === 0 && <li className="p-3 text-sm text-slate-500">Searching…</li>}
          {!isFetching && data.length === 0 && <li className="p-3 text-sm text-slate-500">No matching patients</li>}
          {data.map((p) => (
            <li key={p.id}>
              <button
                type="button"
                className="w-full text-left p-3 hover:bg-teal-50 cursor-pointer bg-transparent border-0"
                onClick={() => onSelect(p)}
              >
                <div className="font-semibold text-slate-900">{p.full_name}</div>
                <div className="text-xs text-slate-500">
                  {p.patient_identifier ? `ID ${p.patient_identifier}` : 'No ID'} · {p.gender} ·{' '}
                  {p.report_count} report{p.report_count === 1 ? '' : 's'}
                  {p.latest_study_date ? ` · last ${formatStudyDate(p.latest_study_date)}` : ''}
                </div>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
