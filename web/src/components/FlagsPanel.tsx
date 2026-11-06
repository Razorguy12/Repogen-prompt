/**
 * Amber "Needs your attention" panel. Renders nothing when there are no flags.
 * When `acknowledged` and `onToggle` are given, each flag gets a checkbox.
 */
export function FlagsPanel({
  flags,
  acknowledged,
  onToggle,
  title = 'Needs your attention',
}: {
  flags: string[]
  acknowledged?: Record<number, string>
  onToggle?: (index: number, checked: boolean) => void
  title?: string
}) {
  if (!flags?.length) return null
  const done = acknowledged ? flags.filter((_, i) => acknowledged[i]).length : 0
  return (
    <section role="alert" className="rounded-xl border border-amber-300 bg-amber-50 p-4 my-3 text-amber-950">
      <div className="flex items-center justify-between gap-3 mb-2">
        <h4 className="m-0 text-sm font-bold uppercase tracking-wider">⚠ {title}</h4>
        {onToggle && <span className="text-xs font-semibold">{done}/{flags.length} acknowledged</span>}
      </div>
      <ul className="m-0 p-0 list-none space-y-2">
        {flags.map((flag, i) => (
          <li key={i} className="flex items-start gap-2 text-sm leading-6">
            {onToggle ? (
              <label className="flex items-start gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  className="mt-1.5 accent-amber-600"
                  checked={!!acknowledged?.[i]}
                  onChange={(e) => onToggle(i, e.target.checked)}
                />
                <span>{flag}</span>
              </label>
            ) : (
              <span>• {flag}</span>
            )}
          </li>
        ))}
      </ul>
    </section>
  )
}
