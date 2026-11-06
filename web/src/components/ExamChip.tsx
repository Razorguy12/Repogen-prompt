import type { ExamInfo } from '../types'

/** Read-only summary of what the model understood, e.g. "US · Abdomen · Not applicable". */
export function ExamChip({ exam }: { exam: ExamInfo | null | undefined }) {
  if (!exam) return null
  const unspecified = exam.modality === 'UNSPECIFIED'
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-semibold ${
        unspecified ? 'border-amber-300 bg-amber-50 text-amber-900' : 'border-teal-200 bg-teal-50 text-teal-900'
      }`}
      title="Examination as understood from your input"
    >
      <span className={unspecified ? 'font-bold' : ''}>{unspecified ? 'Modality not specified' : exam.modality}</span>
      <span aria-hidden>·</span>
      <span>{exam.region}</span>
      <span aria-hidden>·</span>
      <span>{exam.laterality}</span>
    </span>
  )
}
