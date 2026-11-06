import { Fragment, type ReactNode } from 'react'

/**
 * Minimal, safe Markdown renderer for report text. Supports the subset the
 * prompt emits (#/##/### headings, **bold**, *italic*, - / 1. lists,
 * paragraphs). Produces React elements only; raw HTML is never injected.
 */
function inline(text: string): ReactNode[] {
  const out: ReactNode[] = []
  const re = /(\*\*[^*]+\*\*|\*[^*\s][^*]*\*)/g
  let last = 0
  let m: RegExpExecArray | null
  let key = 0
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(text.slice(last, m.index))
    const tok = m[0]
    out.push(tok.startsWith('**')
      ? <strong key={key++}>{tok.slice(2, -2)}</strong>
      : <em key={key++}>{tok.slice(1, -1)}</em>)
    last = m.index + tok.length
  }
  if (last < text.length) out.push(text.slice(last))
  return out
}

export function MarkdownReport({ text, className = '' }: { text: string; className?: string }) {
  const blocks: ReactNode[] = []
  let para: string[] = []
  let list: { ordered: boolean; items: string[] } | null = null
  let k = 0

  const flushPara = () => {
    if (para.length) {
      blocks.push(
        <p key={k++} className="my-2 leading-7 text-slate-800">
          {para.map((line, i) => <Fragment key={i}>{i > 0 && <br />}{inline(line)}</Fragment>)}
        </p>,
      )
      para = []
    }
  }
  const flushList = () => {
    if (list) {
      const items = list.items.map((it, i) => <li key={i} className="my-1">{inline(it)}</li>)
      blocks.push(list.ordered
        ? <ol key={k++} className="list-decimal pl-6 my-2 text-slate-800">{items}</ol>
        : <ul key={k++} className="list-disc pl-6 my-2 text-slate-800">{items}</ul>)
      list = null
    }
  }

  for (const raw of (text || '').split('\n')) {
    const line = raw.trimEnd()
    const heading = /^(#{1,6})\s+(.*)$/.exec(line)
    const bullet = /^\s*[-*•]\s+(.*)$/.exec(line)
    const numbered = /^\s*\d+[.)]\s+(.*)$/.exec(line)
    if (!line.trim()) { flushPara(); flushList(); continue }
    if (heading) {
      flushPara(); flushList()
      const level = heading[1].length
      const cls = level <= 2
        ? 'text-lg font-bold tracking-wide text-slate-900 mt-1 mb-3'
        : 'text-sm font-bold uppercase tracking-wider text-teal-800 mt-4 mb-1'
      blocks.push(level <= 2 ? <h3 key={k++} className={cls}>{inline(heading[2])}</h3> : <h4 key={k++} className={cls}>{inline(heading[2])}</h4>)
      continue
    }
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
  flushPara(); flushList()
  return <div className={className}>{blocks}</div>
}
