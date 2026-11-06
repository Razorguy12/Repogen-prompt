// Same fixtures as the Python parser (tests/report_sections_cases.json at repo root).
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { parseReport } from '../src/lib/reportSections.ts'

const cases = JSON.parse(readFileSync(new URL('../../tests/report_sections_cases.json', import.meta.url), 'utf8'))

for (const c of cases) {
  test(`parser: ${c.name}`, () => {
    const parsed = parseReport(c.full_report, c.title, c.report_format)
    assert.equal(parsed.title, c.expected.title)
    assert.deepEqual(parsed.sections.map((s) => [s.heading, s.body]), c.expected.sections)
    assert.deepEqual(parsed.sections.map((s) => s.isImpression), c.expected.impression)
  })
}
