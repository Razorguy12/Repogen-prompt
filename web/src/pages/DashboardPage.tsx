import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { AppHeader } from '../components/AppHeader'
import { ReportCard } from '../components/ReportCard'
import { SkeletonCard } from '../components/LoadingOverlay'
import { useAuth } from '../context/AuthContext'
import { getReports, getDashboardStats } from '../api/reports'
import { getRecentFinalReports } from '../api/clinical'
import { formatStudyDate, parseUtc } from '../lib/reportText'

export default function DashboardPage() {
  const { name, token } = useAuth()
  const [search, setSearch] = useState('')
  const [modalityFilter, setModalityFilter] = useState<string | null>(null)

  const { data: reports = [], isLoading, isError, error, refetch } = useQuery({
    queryKey: ['reports', token],
    queryFn: getReports,
    enabled: !!token,
  })

  const { data: stats } = useQuery({
    queryKey: ['dashboard-stats', token],
    queryFn: getDashboardStats,
    enabled: !!token,
  })

  const { data: recentFinals = [] } = useQuery({
    queryKey: ['recent-final-reports', token],
    queryFn: () => getRecentFinalReports(10),
    enabled: !!token,
  })

  const modalities = useMemo(() => {
    const set = new Set(reports.map((r) => r.modality).filter(Boolean))
    return Array.from(set).sort()
  }, [reports])

  const filtered = useMemo(() => {
    let result = reports.filter((r) => {
      const term = search.toLowerCase()
      const modality = (r.modality ?? '').toLowerCase()
      const date = parseUtc(r.created_at)
      const dateText = [
        r.created_at,
        date.toLocaleDateString(),
        date.toLocaleDateString(undefined, { month: 'long', day: 'numeric', year: 'numeric' }),
      ].join(' ').toLowerCase()
      const matchesSearch = !term || modality.includes(term) || dateText.includes(term)
      const matchesModality = !modalityFilter || r.modality === modalityFilter
      return matchesSearch && matchesModality
    })

    return result
  }, [reports, search, modalityFilter])

  return (
    <div className="min-h-screen flex flex-col">
      <AppHeader />
      <main className="flex-1 max-w-7xl mx-auto w-full px-4 sm:px-6 py-6 sm:py-8">
        <div className="flex flex-wrap justify-between items-center gap-3 sm:gap-4 mb-6 sm:mb-8">
          <h1 className="text-2xl sm:text-3xl font-bold text-primary-dark m-0">Welcome, {name}</h1>
          <div className="flex flex-wrap gap-2">
            <Link to="/compare" className="btn btn-secondary text-sm sm:text-base py-2 px-3.5 sm:px-4">
              Compare reports
            </Link>
            <Link to="/generate" className="btn btn-primary text-sm sm:text-base py-2 px-3.5 sm:px-4">
              + New Report
            </Link>
          </div>
        </div>

        {recentFinals.length > 0 && (
          <section className="glass-panel p-4 sm:p-5 mb-6 sm:mb-8">
            <h3 className="text-slate-500 font-medium mt-0 mb-3">Recent final reports</h3>
            <ul className="list-none p-0 m-0 divide-y divide-slate-100">
              {recentFinals.map((r) => (
                <li key={r.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                  <Link to={`/final/${r.id}`} className="no-underline text-slate-800 hover:text-primary min-w-0">
                    <strong>{r.patient.full_name}</strong>
                    <span className="text-slate-500 text-sm"> · {r.exam_title} · {formatStudyDate(r.study_date)}</span>
                  </Link>
                  <Link to={`/compare?patient=${r.patient.id}&report=${r.id}`} className="text-sm font-semibold text-primary">
                    Compare
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        )}

        {stats && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 sm:gap-4 mb-6 sm:mb-8">
            {[
              { label: 'Total Reports', value: stats.total },
              { label: 'This Week', value: stats.this_week },
              { label: 'Drafts', value: stats.drafts },
              { label: 'Modalities', value: Object.keys(stats.by_modality).length },
            ].map((s) => (
              <div key={s.label} className="glass-panel p-3 sm:p-4 text-center">
                <div className="text-xl sm:text-2xl font-bold text-primary">{s.value}</div>
                <div className="text-xs sm:text-sm text-slate-500">{s.label}</div>
              </div>
            ))}
          </div>
        )}

        <div className="flex flex-wrap gap-3 sm:gap-4 mb-6">
          <input
            type="text"
            className="form-control w-full sm:max-w-sm"
            placeholder="Search by date or study type..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>

        {modalities.length > 0 && (
          <div className="flex flex-wrap gap-2 mb-6">
            <button
              onClick={() => setModalityFilter(null)}
              className={`px-3 py-1 rounded-full text-sm font-medium cursor-pointer border transition-colors ${
                !modalityFilter
                  ? 'bg-primary text-white border-primary'
                  : 'bg-white/80 text-primary border-primary/20 hover:bg-white'
              }`}
            >
              All
            </button>
            {modalities.map((m) => (
              <button
                key={m}
                onClick={() => setModalityFilter(m === modalityFilter ? null : m)}
                className={`px-3 py-1 rounded-full text-sm font-medium cursor-pointer border transition-colors ${
                  modalityFilter === m
                    ? 'bg-primary text-white border-primary'
                    : 'bg-white/80 text-primary border-primary/20 hover:bg-white'
                }`}
              >
                {m}
              </button>
            ))}
          </div>
        )}

        <h3 className="text-slate-500 font-medium mb-4">Reports by date</h3>

        {isError ? (
          <div className="glass-panel p-8 text-center">
            <p className="text-red-500 mb-2">Failed to load reports</p>
            <p className="text-slate-600 text-sm mb-4">{error instanceof Error ? error.message : 'Unknown error'}</p>
            <button onClick={() => refetch()} className="btn btn-primary">Retry</button>
          </div>
        ) : isLoading ? (
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {[1, 2, 3].map((i) => <SkeletonCard key={i} />)}
          </div>
        ) : filtered.length === 0 ? (
          <div className="glass-panel p-12 text-center">
            <div className="text-5xl mb-4">📋</div>
            <h3 className="text-xl font-semibold text-primary-dark mb-2">No reports yet</h3>
            <p className="text-slate-600 mb-2">Create your first AI-assisted radiology report.</p>
            {reports.length === 0 && stats && stats.total === 0 && (
              <p className="text-slate-500 text-sm mb-6">
                Reports are tied to your account ({name}). If you expected to see reports here, try signing in with the account that created them.
              </p>
            )}
            <Link to="/generate" className="btn btn-primary">Create Your First Report</Link>
          </div>
        ) : (
          <div className="space-y-8">
            {Object.entries(
              filtered.reduce<Record<string, typeof filtered>>((acc, r) => {
                const key = parseUtc(r.created_at).toLocaleDateString(undefined, {
                  weekday: 'long',
                  day: 'numeric',
                  month: 'long',
                  year: 'numeric',
                })
                acc[key] = acc[key] ? [...acc[key], r] : [r]
                return acc
              }, {}),
            ).map(([label, items]) => (
              <section key={label}>
                <h4 className="text-xs font-bold tracking-[0.16em] uppercase text-slate-400 mb-3">{label}</h4>
                <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
                  {items.map((r) => <ReportCard key={r.id} report={r} />)}
                </div>
              </section>
            ))}
          </div>
        )}
      </main>
    </div>
  )
}
