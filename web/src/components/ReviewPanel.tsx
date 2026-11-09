import type { ReviewFlag, ReviewStatus } from '../types'

export interface PendingCorrection { flagId: number; itemIndex: number | null }

interface Props {
  flags: ReviewFlag[]
  pending: PendingCorrection[]
  readOnly?: boolean
  onReview: (flag: ReviewFlag, status: ReviewStatus, itemIndex: number | null) => void
  onCorrect: (flag: ReviewFlag, itemIndex: number | null, text: string) => void
}

const statusLabel: Record<string, string> = { confirmed: 'Confirmed', corrected: 'Corrected', not_applicable: 'Not applicable' }

/** Review units count once per item for assumed-absent flags and once per flag otherwise. */
export function reviewCounts(flags: ReviewFlag[]) {
  let total = 0
  let done = 0
  for (const f of flags.filter((x) => x.requires_review)) {
    if (f.type === 'assumed_absent') {
      total += f.items.length
      done += f.items.filter((i) => i.status !== 'open').length
    } else {
      total += 1
      if (f.status !== 'open') done += 1
    }
  }
  return { total, done }
}

export function ReviewPanel({ flags, pending, readOnly, onReview, onCorrect }: Props) {
  const { total, done } = reviewCounts(flags)
  const isPending = (flagId: number, i: number | null) => pending.some((p) => p.flagId === flagId && p.itemIndex === i)
  const undo = (f: ReviewFlag, i: number | null) =>
    !readOnly && <button type="button" className="review-link" onClick={() => onReview(f, 'open', i)}>Undo</button>
  const done_ = (status: string) => <span className="review-done">{statusLabel[status] ?? status}</span>

  const confirmAll = (f: ReviewFlag) => {
    if (!pending.some((p) => p.flagId === f.id)) return onReview(f, 'confirmed', null)
    f.items.forEach((item, i) => {
      if (item.status === 'open' && !isPending(f.id, i)) onReview(f, 'confirmed', i)
    })
  }

  return (
    <aside className="review-panel" id="review-panel" aria-label="Review flags">
      <header>
        <h4>Review</h4>
        <span>{done} of {total} items reviewed</span>
      </header>
      <p className="review-note">The model did not see the images. Assumed statements come from what was not dictated.</p>
      {flags.map((f) => {
        if (f.severity === 'info') return <div key={f.id} className="review-card is-info">{f.raw_text}</div>
        if (f.type === 'assumed_absent') {
          return (
            <div key={f.id} className={`review-card ${f.status === 'open' ? 'is-open' : ''}`}>
              <h5>Assumed absent</h5>
              {f.items.map((item, i) => (
                <div className="review-row" key={i}>
                  <span>{item.text}</span>
                  {item.status !== 'open' ? <>{done_(item.status)}{undo(f, i)}</>
                    : isPending(f.id, i) ? <span className="review-pending">Save your edit</span>
                    : !readOnly && (
                      <span className="review-actions">
                        <button type="button" onClick={() => onReview(f, 'confirmed', i)}>Confirm</button>
                        <button type="button" onClick={() => onCorrect(f, i, item.text)}>Correct</button>
                      </span>
                    )}
                </div>
              ))}
            </div>
          )
        }
        if (f.type === 'assumed_normal') {
          return (
            <details key={f.id} className={`review-card ${f.status === 'open' ? 'is-open' : ''}`}>
              <summary>Assumed normal: {f.items.length} {f.items.length === 1 ? 'structure' : 'structures'}</summary>
              {f.items.map((item, i) => (
                <div className="review-row" key={i}>
                  <span>{item.text}</span>
                  {item.status !== 'open' ? <>{done_(item.status)}{undo(f, i)}</>
                    : isPending(f.id, i) ? <span className="review-pending">Save your edit</span>
                    : !readOnly && (
                      <span className="review-actions">
                        <button type="button" onClick={() => onCorrect(f, i, item.text)}>Not normal</button>
                      </span>
                    )}
                </div>
              ))}
              {!readOnly && f.status === 'open' && (
                <button type="button" className="review-primary" onClick={() => confirmAll(f)}>Confirm all normal</button>
              )}
            </details>
          )
        }
        return (
          <div key={f.id} className={`review-card ${f.status === 'open' ? 'is-open' : ''}`}>
            <p>{f.raw_text}</p>
            {f.status !== 'open' ? <>{done_(f.status)}{undo(f, null)}</> : !readOnly && (
              <span className="review-actions">
                <button type="button" onClick={() => onReview(f, 'confirmed', null)}>Resolve</button>
                <button type="button" onClick={() => onReview(f, 'not_applicable', null)}>Not applicable</button>
              </span>
            )}
          </div>
        )
      })}
    </aside>
  )
}
