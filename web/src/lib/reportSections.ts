/**
 * Split full_report into a title and headed sections.
 * Mirror of model/report_sections.py — both are tested against
 * tests/report_sections_cases.json. Keep them in step.
 */

const KNOWN_HEADINGS = new Set([
  'clinical details', 'clinical detail', 'clinical history', 'clinical indication', 'clinical information',
  'clinical data', 'indication', 'indications', 'history', 'clinical profile',
  'protocol', 'technique', 'procedure', 'examination', 'study', 'exam', 'comparison',
  'observations', 'observation', 'findings', 'finding', 'report',
  'impression', 'impressions', 'conclusion', 'conclusions', 'opinion', 'summary',
  'recommendation', 'recommendations', 'advice', 'suggestion', 'note', 'notes',
])
const IMPRESSION_WORDS = ['impression', 'conclusion', 'opinion']
const MAX_HEADING_LEN = 60

export interface ReportSection {
  heading: string | null
  body: string
  isImpression: boolean
}

export interface ParsedReport {
  title: string | null
  sections: ReportSection[]
}

function key(text: string): string {
  return text
    .replace(/[*_#`]/g, '')
    .replace(/\([^)]*\)/g, '')
    .trim()
    .replace(/:$/, '')
    .trim()
    .replace(/\s+/g, ' ')
    .toLowerCase()
}

export function formatHeadings(reportFormat?: string | null): Set<string> {
  const names = new Set<string>()
  for (const line of (reportFormat || '').split('\n')) {
    for (const part of line.split(/[,:;/]/)) {
      const k = key(part)
      if (k && k.length <= MAX_HEADING_LEN && !['title', 'organ-wise', 'organ wise'].includes(k)) names.add(k)
    }
  }
  return names
}

function cleanHeading(text: string): string {
  return text.replace(/[*_#`]/g, '').replace(/\s+/g, ' ').trim().replace(/:$/, '').trim()
}

function matchHeading(line: string, extra: Set<string>): [string, string] | null {
  const s = line.trim()
  if (!s) return null
  let m = /^#{1,6}\s+(.+?)\s*#*\s*$/.exec(s)
  if (m) return [cleanHeading(m[1]), '']
  m = /^\*\*([^*]+?)\*\*\s*(:?)\s*(.*)$/.exec(s)
  if (m) {
    const [, label, colon, rest] = m
    if ((label.trimEnd().endsWith(':') || colon || !rest) && cleanHeading(label).length <= MAX_HEADING_LEN) {
      return [cleanHeading(label), rest.trim()]
    }
  }
  const known = (k: string) => KNOWN_HEADINGS.has(k) || extra.has(k)
  if (s.length <= MAX_HEADING_LEN && known(key(s))) return [cleanHeading(s), '']
  m = /^([A-Za-z][A-Za-z /&()-]{1,40}):\s+(.+)$/.exec(s)
  if (m && known(key(m[1]))) return [cleanHeading(m[1]), m[2].trim()]
  return null
}

export function parseReport(fullReport: string, title?: string | null, reportFormat?: string | null): ParsedReport {
  const extra = formatHeadings(reportFormat)
  const titleKey = title ? key(title) : null
  const sections: { heading: string | null; lines: string[] }[] = []
  let current: { heading: string | null; lines: string[] } = { heading: null, lines: [] }
  let parsedTitle: string | null = null
  let seenContent = false
  const hasContent = (sec: { heading: string | null; lines: string[] }) =>
    sec.heading !== null || sec.lines.join('\n').trim() !== ''

  for (const raw of (fullReport || '').replace(/\r\n/g, '\n').split('\n')) {
    const line = raw.trimEnd()
    const hit = matchHeading(line, extra)
    if (!seenContent && parsedTitle === null && line.trim()) {
      const isTopMd = /^#{1,2}\s/.test(line.trim())
      const candidate = hit ? hit[0] : cleanHeading(line)
      if ((titleKey && key(candidate) === titleKey) || (isTopMd && !(hit && KNOWN_HEADINGS.has(key(hit[0]))))) {
        parsedTitle = candidate
        continue
      }
    }
    if (hit) {
      if (hasContent(current)) sections.push(current)
      current = { heading: hit[0], lines: hit[1] ? [hit[1]] : [] }
      seenContent = true
      continue
    }
    if (line.trim()) seenContent = true
    current.lines.push(line)
  }
  if (hasContent(current)) sections.push(current)

  return {
    title: parsedTitle ?? title ?? null,
    sections: sections.map((sec) => {
      const lines = [...sec.lines]
      while (lines.length && !lines[0].trim()) lines.shift()
      while (lines.length && !lines[lines.length - 1].trim()) lines.pop()
      return {
        heading: sec.heading,
        body: lines.join('\n'),
        isImpression: !!sec.heading && IMPRESSION_WORDS.some((w) => sec.heading!.toLowerCase().includes(w)),
      }
    }),
  }
}

/** Words in section bodies only (title and headings excluded), as the prompt counts. */
export function bodyWordCount(fullReport: string, title?: string | null, reportFormat?: string | null): number {
  const text = parseReport(fullReport, title, reportFormat).sections.map((s) => s.body).join(' ')
  return text.replace(/[*_`>#]/g, ' ').split(/\s+/).filter((w) => /[\p{L}\p{N}]/u.test(w)).length
}
