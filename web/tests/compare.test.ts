// Run with: npm test   (node --test, native TypeScript type stripping)
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { filterReports, intervalDays, orderPair } from '../src/lib/compare.ts'
import { countBodyWords, formatDateTime, formatStudyDate, parseUtc } from '../src/lib/reportText.ts'

const r = (id: number, modality: string, region: string, study_date: string) =>
  ({ id, exam: { modality, region, laterality: 'Not applicable' }, study_date }) as never

const reports = [
  r(1, 'XR', 'Chest', '2026-10-23'),
  r(2, 'XR', 'Chest', '2026-11-06'),
  r(3, 'CT', 'Chest', '2026-09-01'),
  r(4, 'US', 'Abdomen', '2026-08-01'),
]
const none = { modalities: [], regions: [], from: '', to: '', sameExamOnly: true }

test('filters combine with AND', () => {
  const ids = filterReports(reports, { ...none, modalities: ['XR', 'CT'], regions: ['Chest'], from: '2026-10-01' }, null, [])
    .map((x: { id: number }) => x.id)
  assert.deepEqual(ids, [1, 2])
})

test('same exam only narrows after first selection, keeps selection visible', () => {
  assert.equal(filterReports(reports, none, null, []).length, 4)
  const ids = filterReports(reports, none, reports[0], [1]).map((x: { id: number }) => x.id)
  assert.deepEqual(ids, [1, 2])
  assert.equal(filterReports(reports, { ...none, sameExamOnly: false }, reports[0], [1]).length, 4)
})

test('baseline is the earlier study date; interval in days', () => {
  const { baseline, followup } = orderPair(reports[1], reports[0], null)
  assert.equal((baseline as { id: number }).id, 1)
  assert.equal(intervalDays(baseline, followup), 14)
})

test('same-date pair honours the chosen baseline', () => {
  const a = r(5, 'XR', 'Chest', '2026-11-06')
  const b = r(6, 'XR', 'Chest', '2026-11-06')
  assert.equal((orderPair(a, b, 6).baseline as { id: number }).id, 6)
})

test('timestamps: 12:01 UTC displays as 17:31 IST; naive strings are UTC', () => {
  assert.equal(formatDateTime('2026-11-06T12:01:00Z'), '06 Nov 2026, 5:31 PM IST')
  assert.equal(formatDateTime('2026-11-06T12:01:00'), '06 Nov 2026, 5:31 PM IST')
  assert.equal(parseUtc('2026-11-06T12:01:00').toISOString(), '2026-11-06T12:01:00.000Z')
})

test('around midnight IST the calendar date flips correctly', () => {
  assert.equal(formatDateTime('2026-11-06T18:29:00Z'), '06 Nov 2026, 11:59 PM IST')
  assert.equal(formatDateTime('2026-11-06T18:31:00Z'), '07 Nov 2026, 12:01 AM IST')
  assert.equal(formatStudyDate('2026-11-07'), '07 Nov 2026')
})

test('word count excludes title and headings', () => {
  const text = '## CHEST RADIOGRAPH\n\n**Clinical Details:**\nCough.\n\n**Observations:** Lungs are clear.\n\n### IMPRESSION\nNormal study.'
  assert.equal(countBodyWords(text), 6)
})
