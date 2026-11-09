export interface RadiologyFinding {
  location: string
  description: string
  severity: 'mild' | 'moderate' | 'severe'
}

export interface RadiologyReport {
  patient_name: string
  patient_id: string
  study_date: string
  modality: string
  study_type: string
  protocol?: string | null
  findings: RadiologyFinding[]
  impression: string
  recommendations?: string[] | null
  radiologist_name?: string | null
  scan_image?: string | null
  scan_image_name?: string | null
}

export type ReportKind = 'prompt' | 'structured'

export interface ReportAlternative {
  type: 'concise' | 'standard' | 'detailed'
  word_limit: string
  title: string
  clinical_details: string
  protocol: string
  observations: string
  impression: string
  full_report: string
}

export type Modality = 'XR' | 'CT' | 'MRI' | 'US' | 'DOPPLER' | 'MAMMO' | 'FLUORO' | 'OTHER' | 'UNSPECIFIED'
export type Laterality = 'Left' | 'Right' | 'Bilateral' | 'Not applicable' | 'Not specified'
export const MODALITIES: Modality[] = ['XR', 'CT', 'MRI', 'US', 'DOPPLER', 'MAMMO', 'FLUORO', 'OTHER', 'UNSPECIFIED']
export const LATERALITIES: Laterality[] = ['Left', 'Right', 'Bilateral', 'Not applicable', 'Not specified']

export interface ExamInfo {
  modality: Modality
  region: string
  laterality: Laterality
}

export interface PromptInputParams {
  kind?: ReportKind
  prompt?: string
  report_format?: string
  selected?: string
  alternatives?: ReportAlternative[]
  /** Absent on drafts created before prompt v2. */
  exam?: ExamInfo | null
  flags?: string[]
  prompt_version?: string
}

export interface ReportSummary {
  id: number
  patient_id: string
  patient_name: string
  modality: string
  status: 'draft' | 'final'
  kind?: ReportKind
  created_at: string
  updated_at: string
  report_data: RadiologyReport | ReportAlternative
  input_params?: (Partial<ReportInputParams> & PromptInputParams) | null
  scan_image?: string | null
  scan_image_name?: string | null
  /** Current signed version and its patient, when this draft has been finalized. */
  final_report?: FinalSummary | null
}

export interface FinalSummary {
  id: number
  status: 'final' | 'amended'
  patient_id: number
  patient_name: string
  patient_identifier: string | null
  exam_title: string
  study_date: string
}

export interface ReportFormatPreset { id: string; label: string; description: string; format_text: string }
export interface ReportFormatOptions { presets: ReportFormatPreset[]; default_id: string; custom: string; max_custom_chars: number }

export type ReviewStatus = 'open' | 'confirmed' | 'corrected' | 'not_applicable'

export interface ReviewFlag {
  id: number
  type: string
  severity: 'high' | 'medium' | 'info'
  raw_text: string
  items: { text: string; status: ReviewStatus }[]
  source: 'model' | 'server'
  requires_review: boolean
  status: ReviewStatus
  reviewed_by: number | null
  reviewed_at: string | null
}

export interface PromptSession {
  id: number
  created_at: string
  selected: string
  reports: ReportAlternative[]
  prompt: string
  report_format?: string
  status?: 'draft' | 'final'
  exam?: ExamInfo | null
  flags?: string[]
  prompt_version?: string | null
}

export interface ReportInputParams {
  patient_info: string
  study_info: string
  clinical_info?: string
  radiologist_findings?: string
  scan_image?: string | null
  scan_image_name?: string | null
}

export interface PdfExtractionResponse {
  filename: string
  page_count: number
  text: string
  has_text: boolean
  message?: string
}

export interface AudioTranscriptionResponse {
  text: string
  filename: string
}

export interface GenerateReportResponse {
  id: number
  report: RadiologyReport
}

export interface DashboardStats {
  total: number
  this_week: number
  drafts: number
  by_modality: Record<string, number>
}

export interface UserProfile {
  name: string
  username: string
  email: string
  is_admin: boolean
  is_root_admin?: boolean
}

export interface AdminUser {
  id: number
  name: string
  username: string
  email: string
  is_admin: boolean
  is_locked: boolean
  is_root_admin?: boolean
  report_count: number
}

export interface StudyTemplate {
  id: string
  name: string
  modality: string
  study_type: string
  study_info: string
  clinical_info?: string
}

export interface AuthState {
  token: string | null
  name: string | null
  isAdmin: boolean
}

export interface LoginResponse {
  access_token: string
  token_type: string
  is_admin: boolean
  name: string
}
