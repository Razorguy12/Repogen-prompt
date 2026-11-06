import { apiFetch, apiFetchBlob } from './client'
import type {
  Comparison, ComparisonListItem, FinalReport, FinalReportSummary, FinalizeRequest, Patient, PatientInput,
} from '../types/clinical'

export const searchPatients = (q: string) =>
  apiFetch<Patient[]>(`/api/patients?q=${encodeURIComponent(q)}`)

export const getPatient = (id: number) => apiFetch<Patient>(`/api/patients/${id}`)

export const checkDuplicatePatients = (body: { full_name: string; patient_identifier?: string | null }) =>
  apiFetch<Patient[]>('/api/patients/duplicates', { method: 'POST', body: JSON.stringify(body) })

export const updatePatient = (id: number, body: PatientInput) =>
  apiFetch<Patient>(`/api/patients/${id}`, { method: 'PATCH', body: JSON.stringify(body) })

export const getAgeSuggestion = (patientId: number, studyDate: string) =>
  apiFetch<{ value: number; unit: 'years' | 'months' | 'days' } | null>(
    `/api/patients/${patientId}/age-suggestion?study_date=${studyDate}`)

export const getPatientFinalReports = (patientId: number) =>
  apiFetch<FinalReportSummary[]>(`/api/patients/${patientId}/final-reports`)

export const finalizeDraft = (draftId: number, body: FinalizeRequest) =>
  apiFetch<FinalReport>(`/api/reports/${draftId}/finalize`, { method: 'POST', body: JSON.stringify(body) })

export const getFinalReportForDraft = (draftId: number) =>
  apiFetch<{ id: number }>(`/api/final-reports/by-draft/${draftId}`)

export const getRecentFinalReports = (limit = 10, q = '') =>
  apiFetch<FinalReportSummary[]>(`/api/final-reports?limit=${limit}${q ? `&q=${encodeURIComponent(q)}` : ''}`)

export const getFinalReport = (id: number) => apiFetch<FinalReport>(`/api/final-reports/${id}`)

export const amendFinalReport = (id: number, finalText: string) =>
  apiFetch<FinalReport>(`/api/final-reports/${id}/amend`, {
    method: 'POST', body: JSON.stringify({ final_text: finalText }),
  })

export const recordFinalReportExport = (id: number, format: 'print' | 'copy') =>
  apiFetch<void>(`/api/final-reports/${id}/export-event?format=${format}`, { method: 'POST' })

export const generateComparison = (baselineId: number, followupId: number) =>
  apiFetch<Comparison>('/api/comparisons', {
    method: 'POST', body: JSON.stringify({ report_ids: [baselineId, followupId] }),
  })

export const getComparison = (id: number) => apiFetch<Comparison>(`/api/comparisons/${id}`)

export const saveComparison = (id: number, body: { edited_summary: string; edited_impression: string[] }) =>
  apiFetch<Comparison>(`/api/comparisons/${id}`, { method: 'PATCH', body: JSON.stringify({ ...body, status: 'saved' }) })

export const regenerateComparison = (id: number) =>
  apiFetch<Comparison>(`/api/comparisons/${id}/regenerate`, { method: 'POST' })

export const getPatientComparisons = (patientId: number) =>
  apiFetch<ComparisonListItem[]>(`/api/patients/${patientId}/comparisons`)

export async function downloadFinalReport(id: number, format: 'pdf' | 'docx'): Promise<void> {
  const blob = await apiFetchBlob(`/api/final-reports/${id}/export?format=${format}`, { method: 'GET' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `final_report_${id}.${format}`
  a.click()
  URL.revokeObjectURL(url)
}
