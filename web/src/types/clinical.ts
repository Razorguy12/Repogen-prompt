import type { ExamInfo, Laterality, Modality } from './index'

export type Gender = 'Male' | 'Female' | 'Other' | 'Not stated'
export const GENDERS: Gender[] = ['Male', 'Female', 'Other', 'Not stated']
export type AgeUnit = 'years' | 'months' | 'days'
export const AGE_UNITS: AgeUnit[] = ['years', 'months', 'days']

export interface Patient {
  id: number
  full_name: string
  patient_identifier: string | null
  gender: Gender
  report_count: number
  latest_study_date: string | null
  created_at: string
  updated_at: string
  last_age?: { value: number; unit: AgeUnit; study_date: string } | null
}

export interface PatientInput {
  full_name: string
  patient_identifier?: string | null
  gender: Gender
}

export interface FinalReportSummary {
  id: number
  draft_id: number
  status: 'final' | 'amended'
  amends_report_id: number | null
  superseded_by_id: number | null
  patient: Patient
  doctor_name: string | null
  selected_variant: 'concise' | 'standard' | 'detailed'
  exam: { modality: Modality; region: string; laterality: Laterality | string }
  exam_title: string
  age: { value: number; unit: AgeUnit }
  study_date: string
  finalized_at: string
  created_at: string
  updated_at: string
}

export interface FinalReport extends FinalReportSummary {
  final_text: string
  /** House format used when the draft was generated; helps detect custom headings. */
  report_format?: string | null
  final_sections: Record<string, string> | null
  flags: string[]
  flag_acknowledgements: { flag: string; acknowledged_at: string }[]
  flags_acknowledged_at: string | null
  prompt_version: string | null
  model_id: string | null
  previous_versions?: { id: number; status: string; finalized_at: string }[]
  comparisons?: ComparisonListItem[]
}

export interface FinalizeRequest {
  selected_variant: string
  patient_id?: number | null
  new_patient?: PatientInput | null
  create_new_anyway?: boolean
  age_value: number
  age_unit: AgeUnit
  study_date: string
  exam: ExamInfo
  flag_acknowledgements: { index: number; acknowledged_at: string }[]
  approved: boolean
}

export interface DuplicateDetail {
  code: 'possible_duplicate' | 'identifier_in_use'
  message: string
  matches: Patient[]
}

export type ChangeCategory = 'NEW' | 'RESOLVED' | 'INCREASED' | 'DECREASED' | 'STABLE' | 'NOT COMPARABLE'

export interface ComparisonResult {
  comparison_title: string
  interval_days: number
  examinations_comparable: boolean
  summary: string
  changes: { finding: string; category: ChangeCategory; baseline: string; follow_up: string; note: string }[]
  comparison_impression: string[]
  limitations: string[]
  flags: string[]
}

export interface ComparisonListItem {
  id: number
  status: 'draft' | 'saved'
  created_at: string
  interval_days: number
  baseline_report_id: number
  followup_report_id: number
  baseline_study_date?: string
  followup_study_date?: string
}

export interface Comparison extends ComparisonListItem {
  patient: Patient
  baseline: FinalReport
  followup: FinalReport
  result: ComparisonResult
  edited_summary: string | null
  edited_impression: string[] | null
  prompt_version: string | null
  model_id: string | null
  updated_at: string
}
