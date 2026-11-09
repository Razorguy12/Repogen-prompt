import type { ReportFormatOptions, ReviewFlag, ReviewStatus } from '../types'
import { apiFetch, apiFetchBlob } from './client'
import { getToken } from './client'
import type {
  AdminUser,
  DashboardStats,
  GenerateReportResponse,
  PromptSession,
  RadiologyReport,
  ReportAlternative,
  ReportInputParams,
  ReportSummary,
  StudyTemplate,
  UserProfile,
  LoginResponse,
  PdfExtractionResponse,
  AudioTranscriptionResponse,
} from '../types'

export async function extractTextFromPdf(file: File): Promise<PdfExtractionResponse> {
  const formData = new FormData()
  formData.append('file', file)
  return apiFetch<PdfExtractionResponse>('/api/extract-text-from-pdf', {
    method: 'POST',
    body: formData,
  })
}

export async function transcribeAudio(file: Blob | File, filename = 'dictation.webm'): Promise<AudioTranscriptionResponse> {
  const formData = new FormData()
  formData.append('file', file, filename)
  return apiFetch<AudioTranscriptionResponse>('/api/transcribe-audio', {
    method: 'POST',
    body: formData,
  })
}

export async function login(username: string, password: string): Promise<LoginResponse> {
  const formData = new URLSearchParams()
  formData.append('username', username)
  formData.append('password', password)

  return apiFetch<LoginResponse>('/api/token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: formData,
  })
}

export async function getMe(): Promise<UserProfile> {
  return apiFetch<UserProfile>('/api/users/me')
}

export async function logout(reason?: string): Promise<void> {
  return apiFetch<void>(`/api/logout${reason ? `?reason=${encodeURIComponent(reason)}` : ''}`, { method: 'POST' })
}

export async function getReports(): Promise<ReportSummary[]> {
  return apiFetch<ReportSummary[]>('/api/reports')
}

export async function getReport(id: number): Promise<ReportSummary> {
  return apiFetch<ReportSummary>(`/api/reports/${id}`)
}

export async function updateReport(
  id: number,
  reportData: RadiologyReport,
): Promise<ReportSummary> {
  return apiFetch<ReportSummary>(`/api/reports/${id}`, {
    method: 'PATCH',
    body: JSON.stringify({ report_data: reportData }),
  })
}

export async function updateReportStatus(
  id: number,
  status: 'draft' | 'final',
): Promise<ReportSummary> {
  return apiFetch<ReportSummary>(`/api/reports/${id}/status`, {
    method: 'PATCH',
    body: JSON.stringify({ status }),
  })
}

export async function generateReport(
  params: ReportInputParams,
): Promise<GenerateReportResponse> {
  return apiFetch<GenerateReportResponse>('/api/generate-report', {
    method: 'POST',
    body: JSON.stringify(params),
  })
}

export function getReportFormats(): Promise<ReportFormatOptions> {
  return apiFetch('/api/report-formats')
}

export function saveCustomFormat(text: string): Promise<{ custom: string }> {
  return apiFetch('/api/users/me/report-format', { method: 'PUT', body: JSON.stringify({ text }) })
}

export function getDraftFlags(draftId: number): Promise<ReviewFlag[]> {
  return apiFetch(`/api/reports/${draftId}/flags`)
}

export function reviewDraftFlag(
  draftId: number,
  flagId: number,
  status: ReviewStatus,
  itemIndex: number | null,
): Promise<ReviewFlag> {
  return apiFetch(`/api/reports/${draftId}/flags/${flagId}/review`, {
    method: 'POST',
    body: JSON.stringify({ status, item_index: itemIndex }),
  })
}

export async function generateAlternatives(
  prompt: string,
  formatId?: string,
): Promise<PromptSession> {
  return apiFetch('/api/generate-alternatives', {
    method: 'POST',
    body: JSON.stringify({ prompt, format_id: formatId }),
  })
}

export async function updatePromptDraft(
  id: number,
  body: { selected?: string; report?: ReportAlternative },
): Promise<PromptSession> {
  return apiFetch(`/api/reports/${id}/draft`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  })
}

function triggerDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

export async function downloadAlternativePdf(report: ReportAlternative, reportId?: number): Promise<void> {
  const blob = await apiFetchBlob(`/api/alternative-pdf${reportId ? `?report_id=${reportId}` : ''}`, {
    method: 'POST',
    body: JSON.stringify(report),
  })
  triggerDownload(blob, `radiology_report_${report.type}.pdf`)
}

export async function downloadAlternativeDocx(report: ReportAlternative, reportId?: number): Promise<void> {
  const blob = await apiFetchBlob(`/api/alternative-docx${reportId ? `?report_id=${reportId}` : ''}`, {
    method: 'POST',
    body: JSON.stringify(report),
  })
  triggerDownload(blob, `radiology_report_${report.type}.docx`)
}

export async function downloadReportPdf(report: RadiologyReport, reportId?: number): Promise<void> {
  const blob = await apiFetchBlob(`/api/create-pdf-from-report${reportId ? `?report_id=${reportId}` : ''}`, {
    method: 'POST',
    body: JSON.stringify(report),
  })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `radiology_report_${report.patient_id}.pdf`
  a.click()
  URL.revokeObjectURL(url)
}

export async function getDashboardStats(): Promise<DashboardStats> {
  return apiFetch<DashboardStats>('/api/dashboard/stats')
}

export async function getTemplates(): Promise<StudyTemplate[]> {
  return apiFetch<StudyTemplate[]>('/api/templates')
}

export async function getUsers(): Promise<AdminUser[]> {
  return apiFetch<AdminUser[]>('/api/users')
}

export async function createUser(data: {
  name: string
  username: string
  email: string
  password: string
  is_admin: boolean
}): Promise<{ msg: string }> {
  return apiFetch('/api/users', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function updateUserPassword(userId: number, password: string): Promise<{ msg: string }> {
  return apiFetch(`/api/admin/users/${userId}/password`, {
    method: 'PATCH',
    body: JSON.stringify({ password }),
  })
}

export async function deleteDoctor(userId: number): Promise<{ msg: string }> {
  return apiFetch(`/api/admin/users/${userId}`, { method: 'DELETE' })
}

export async function setUserLocked(userId: number, locked: boolean): Promise<{ msg: string }> {
  return apiFetch(`/api/admin/users/${userId}/lock`, {
    method: 'PATCH',
    body: JSON.stringify({ locked }),
  })
}

export async function getUserReports(userId: number): Promise<ReportSummary[]> {
  return apiFetch<ReportSummary[]>(`/api/admin/users/${userId}/reports`)
}

export interface AuditFilters {
  search?: string; user_id?: string; event_type?: string; status?: string;
  resource_id?: string; start_date?: string; end_date?: string; sort_order?: string;
  page?: number; page_size?: number
}
export interface AuditEventRecord {
  id: number; event_type: string; user_id: number | null; username: string | null; email: string | null;
  status: string; resource_type: string | null; resource_id: string | null; ip_address: string | null;
  user_agent: string | null; request_id: string | null; duration_ms: number | null;
  details: Record<string, unknown>; created_at: string
}
export interface AuditPage { items: AuditEventRecord[]; total: number; page: number; page_size: number; total_pages: number }
function filterQuery(filters: AuditFilters) {
  const params = new URLSearchParams()
  Object.entries(filters).forEach(([key, value]) => { if (value !== undefined && value !== '') params.set(key, String(value)) })
  return params.toString()
}
export async function getAuditLogs(filters: AuditFilters): Promise<AuditPage> {
  return apiFetch(`/api/admin/audit-logs?${filterQuery(filters)}`)
}
export async function getAuditStats(filters: Pick<AuditFilters, 'start_date' | 'end_date'>) {
  return apiFetch<{ total_users: number; active_users: number; reports_generated: number; failed_operations: number; total_logins: number; total_downloads: number }>(`/api/admin/audit-stats?${filterQuery(filters)}`)
}
export async function getAuditAnalytics(filters: Pick<AuditFilters, 'start_date' | 'end_date'>) {
  return apiFetch<{ activity: { date: string; logins: number; reports: number; downloads: number }[]; generation: { success: number; failed: number }; users: { user_id: number; username: string; activity_count: number }[] }>(`/api/admin/audit-analytics?${filterQuery(filters)}`)
}
export async function getAuditEvent(id: number): Promise<AuditEventRecord> {
  return apiFetch(`/api/admin/audit-logs/${id}`)
}
export async function getUserActivity(userId: number, filters: Pick<AuditFilters, 'start_date' | 'end_date'>) {
  return apiFetch<{ user: { id: number; name: string; username: string; email: string; is_admin: boolean; is_locked: boolean }; stats: Record<string, number | string | null>; items: AuditEventRecord[]; total: number; page: number; page_size: number }>(`/api/admin/users/${userId}/activity?${filterQuery({ ...filters, page: 1, page_size: 25 })}`)
}
export async function exportAuditLogs(filters: AuditFilters) {
  const token = getToken()
  const headers: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {}
  const response = await fetch(`/api/admin/audit-logs/export?${filterQuery(filters)}`, { headers })
  if (!response.ok) throw new Error(`Export failed (${response.status})`)
  const url = URL.createObjectURL(await response.blob())
  const a = document.createElement('a'); a.href = url; a.download = 'audit-logs.csv'; a.click(); URL.revokeObjectURL(url)
}
