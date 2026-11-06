export function InputTips() {
  return (
    <details className="text-xs text-slate-500 px-1 pt-1">
      <summary className="cursor-pointer select-none font-semibold">Input tips</summary>
      <ul className="mt-1 mb-0 pl-5 list-disc space-y-0.5">
        <li>State the modality and region first, e.g. “USG KUB –” or “CXR PA –”.</li>
        <li>For obstetric scans, include the number of fetuses and cardiac activity.</li>
        <li>For Doppler, give vessel names and values exactly.</li>
      </ul>
    </details>
  )
}
