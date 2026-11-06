import type { FinalReportSummary } from '../types/clinical'

export interface ReportFilters {
  modalities: string[]
  regions: string[]
  from: string // YYYY-MM-DD or ''
  to: string
  sameExamOnly: boolean
}

const norm = (s: string) => s.trim().toLowerCase()

export function sameExam(a: FinalReportSummary, b: FinalReportSummary): boolean {
  return a.exam.modality === b.exam.modality && norm(a.exam.region) === norm(b.exam.region)
}

/**
 * Filters combine with AND. "Same exam only" applies once exactly one report
 * is selected; selected rows always stay visible so they can be unticked.
 */
export function filterReports(
  reports: FinalReportSummary[],
  f: ReportFilters,
  anchor: FinalReportSummary | null,
  selectedIds: number[],
): FinalReportSummary[] {
  return reports.filter((r) => {
    if (selectedIds.includes(r.id)) return true
    if (f.modalities.length && !f.modalities.includes(r.exam.modality)) return false
    if (f.regions.length && !f.regions.includes(r.exam.region)) return false
    if (f.from && r.study_date < f.from) return false
    if (f.to && r.study_date > f.to) return false
    if (f.sameExamOnly && anchor && !sameExam(anchor, r)) return false
    return true
  })
}

/** Baseline is the earlier study_date; on a tie the doctor's choice decides. */
export function orderPair(a: FinalReportSummary, b: FinalReportSummary, baselineChoice: number | null) {
  if (a.study_date === b.study_date) {
    const baseline = baselineChoice === b.id ? b : a
    return { baseline, followup: baseline === a ? b : a }
  }
  return a.study_date < b.study_date ? { baseline: a, followup: b } : { baseline: b, followup: a }
}

export function intervalDays(baseline: FinalReportSummary, followup: FinalReportSummary): number {
  const day = (iso: string) => Date.UTC(+iso.slice(0, 4), +iso.slice(5, 7) - 1, +iso.slice(8, 10))
  return Math.round((day(followup.study_date) - day(baseline.study_date)) / 86_400_000)
}
