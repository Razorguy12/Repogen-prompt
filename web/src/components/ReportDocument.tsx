import { Fragment, type ReactNode } from 'react'
import { parseReport } from '../lib/reportSections'

/** **bold** and *italic* only; React elements, never raw HTML. */
function inline(text: string): ReactNode[] {
  const out: ReactNode[] = []
  const re = /(\*\*[^*]+\*\*|\*[^*\s][^*]*\*)/g
  let last = 0
  let m: RegExpExecArray | null
  let k = 0
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(text.slice(last, m.index))
    out.push(m[0].startsWith('**') ? <strong key={k++}>{m[0].slice(2, -2)}</strong> : <em key={k++}>{m[0].slice(1, -1)}</em>)
    last = m.index + m[0].length
  }
  if (last < text.length) out.push(text.slice(last))
  return out
}

function Body({ text }: { text: string }) {
  const blocks: ReactNode[] = []
  let para: string[] = []
  let list: { ordered: boolean; items: string[] } | null = null
  let k = 0
  const flushPara = () => {
    if (para.length) {
      blocks.push(<p key={k++}>{para.map((l, i) => <Fragment key={i}>{i > 0 && <br />}{inline(l)}</Fragment>)}</p>)
      para = []
    }
  }
  const flushList = () => {
    if (list) {
      const items = list.items.map((it, i) => <li key={i}>{inline(it)}</li>)
      blocks.push(list.ordered ? <ol key={k++}>{items}</ol> : <ul key={k++}>{items}</ul>)
      list = null
    }
  }
  let table: string[] = []
  const flushTable = () => {
    const rows = table
      .filter((l) => !/^\s*\|?[\s:|-]+\|?\s*$/.test(l))
      .map((l) => l.trim().replace(/^\||\|$/g, '').split('|').map((c) => c.trim()))
    table = []
    if (!rows.length) return
    const [head, ...body] = rows
    blocks.push(
      <div className="report-table-wrap" key={k++}>
        <table>
          <thead><tr>{head.map((c, i) => <th key={i}>{inline(c)}</th>)}</tr></thead>
          <tbody>{body.map((r, i) => <tr key={i}>{head.map((_, j) => <td key={j}>{inline(r[j] ?? '')}</td>)}</tr>)}</tbody>
        </table>
      </div>,
    )
  }
  for (const line of text.split('\n')) {
    if (line.trim().startsWith('|')) { flushPara(); flushList(); table.push(line); continue }
    flushTable()
    const bullet = /^\s*[-*•]\s+(.*)$/.exec(line)
    const numbered = /^\s*\d+[.)]\s+(.*)$/.exec(line)
    if (!line.trim()) { flushPara(); flushList(); continue }
    if (bullet || numbered) {
      flushPara()
      const ordered = !!numbered
      if (!list || list.ordered !== ordered) { flushList(); list = { ordered, items: [] } }
      list.items.push((bullet || numbered)![1])
      continue
    }
    flushList()
    para.push(line)
  }
  flushTable(); flushPara(); flushList()
  return <>{blocks}</>
}

/**
 * Renders full_report in the house style: serif title, uppercase blue section
 * headings with dividers, and a shaded Impression box. Used on screen and in print.
 */
export function ReportDocument({
  text, title, reportFormat, showTitle = false,
}: {
  text: string
  title?: string | null
  reportFormat?: string | null
  showTitle?: boolean
}) {
  const parsed = parseReport(text, title, reportFormat)
  return (
    <div className="report-doc">
      {showTitle && parsed.title && <h3 className="report-doc-title">{parsed.title}</h3>}
      {parsed.sections.map((s, i) => (
        <section key={i} className={s.isImpression ? 'impression' : undefined}>
          {s.heading && <h4>{s.heading}</h4>}
          <Body text={s.body} />
        </section>
      ))}
    </div>
  )
}
