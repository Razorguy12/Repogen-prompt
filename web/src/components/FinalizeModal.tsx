import { useEffect, useMemo, useState } from 'react'
import toast from 'react-hot-toast'
import { ApiError } from '../api/client'
import { checkDuplicatePatients, finalizeDraft, getAgeSuggestion, updatePatient } from '../api/clinical'
import { formatStudyDate, todayInClinic } from '../lib/reportText'
import { LATERALITIES, MODALITIES, type ExamInfo, type ReportAlternative } from '../types'
import {
  AGE_UNITS, GENDERS, type AgeUnit, type DuplicateDetail, type FinalReport, type Gender, type Patient,
} from '../types/clinical'
import { ReportDocument } from './ReportDocument'
import { PatientSearch } from './PatientSearch'

type Step = 1 | 2 | 3

interface Props {
  draftId: number
  variant: ReportAlternative
  reportFormat?: string
  exam: ExamInfo | null | undefined
  flagAcks: Record<number, string>
  onClose: () => void
  onFinalized: (report: FinalReport) => void
}

const fieldLabel = 'block text-xs font-bold uppercase tracking-wider text-slate-500 mb-1'

function Segmented<T extends string>({ value, options, onChange, disabled }: {
  value: T | ''
  options: readonly T[]
  onChange: (v: T) => void
  disabled?: boolean
}) {
  return (
    <div role="radiogroup" className="inline-flex flex-wrap rounded-lg border border-slate-300 overflow-hidden">
      {options.map((o) => (
        <button
          key={o}
          type="button"
          role="radio"
          aria-checked={value === o}
          disabled={disabled}
          onClick={() => onChange(o)}
          className={`px-3 py-1.5 text-sm border-0 cursor-pointer disabled:cursor-not-allowed ${
            value === o ? 'bg-primary text-white' : 'bg-white text-slate-700 hover:bg-slate-50'
          }`}
        >
          {o}
        </button>
      ))}
    </div>
  )
}

export function FinalizeModal({ draftId, variant, reportFormat, exam, flagAcks, onClose, onFinalized }: Props) {
  const [step, setStep] = useState<Step>(1)
  const [busy, setBusy] = useState(false)

  // Step 1: patient
  const [existing, setExisting] = useState<Patient | null>(null)
  const [unlocked, setUnlocked] = useState(false)
  const [fullName, setFullName] = useState('')
  const [identifier, setIdentifier] = useState('')
  const [gender, setGender] = useState<Gender | ''>('')
  const [duplicates, setDuplicates] = useState<Patient[] | null>(null)
  const [createAnyway, setCreateAnyway] = useState(false)
  const [identifierClash, setIdentifierClash] = useState(false)

  // Step 2: study
  const today = todayInClinic()
  const [studyDate, setStudyDate] = useState(today)
  const [ageValue, setAgeValue] = useState('')
  const [ageUnit, setAgeUnit] = useState<AgeUnit>('years')
  const [ageTouched, setAgeTouched] = useState(false)
  const [modality, setModality] = useState(exam?.modality ?? 'UNSPECIFIED')
  const [region, setRegion] = useState(exam?.region ?? '')
  const [laterality, setLaterality] = useState<string>(exam?.laterality ?? 'Not specified')

  // Step 3
  const [approved, setApproved] = useState(false)

  const isObstetric = region.trim().toLowerCase() === 'obstetric'

  const selectExisting = (p: Patient) => {
    setExisting(p)
    setUnlocked(false)
    setFullName(p.full_name)
    setIdentifier(p.patient_identifier ?? '')
    setGender(p.gender)
    setDuplicates(null)
    setCreateAnyway(false)
    setIdentifierClash(false)
    setAgeTouched(false)
  }

  const clearExisting = () => {
    setExisting(null)
    setUnlocked(false)
    setFullName('')
    setIdentifier('')
    setGender('')
  }

  // Pre-fill age from the patient's last recorded age plus elapsed time.
  useEffect(() => {
    if (!existing || ageTouched || !studyDate) return
    let cancelled = false
    getAgeSuggestion(existing.id, studyDate)
      .then((s) => {
        if (!cancelled && s) {
          setAgeValue(String(s.value))
          setAgeUnit(s.unit)
        }
      })
      .catch(() => undefined)
    return () => { cancelled = true }
  }, [existing, studyDate, ageTouched])

  const nameValid = fullName.trim().length >= 2 && fullName.trim().length <= 100
  const patientValid = nameValid && !!gender

  const ageNumber = Number(ageValue)
  const ageError = useMemo(() => {
    if (ageValue === '' || !Number.isInteger(ageNumber)) return 'Enter a whole number'
    const max = { years: 130, months: 240, days: 366 }[ageUnit]
    if (ageNumber < 0 || ageNumber > max) return `Must be 0–${max} ${ageUnit}`
    return null
  }, [ageValue, ageNumber, ageUnit])
  const dateError = !studyDate ? 'Required' : studyDate > today ? 'Cannot be in the future' : null
  const studyValid = !ageError && !dateError && modality !== 'UNSPECIFIED' && region.trim().length > 0

  const goToStudy = async () => {
    if (!patientValid) return
    if (existing) {
      if (unlocked) {
        const changed = fullName.trim() !== existing.full_name || gender !== existing.gender
          || (identifier.trim() || null) !== (existing.patient_identifier || null)
        if (changed) {
          if (!window.confirm('Update this patient’s details? This changes the patient record for all of their reports.')) return
          setBusy(true)
          try {
            const updated = await updatePatient(existing.id, {
              full_name: fullName.trim(), patient_identifier: identifier.trim() || null, gender: gender as Gender,
            })
            setExisting(updated)
            setUnlocked(false)
            toast.success('Patient details updated')
          } catch (err) {
            toast.error(err instanceof ApiError ? err.message : 'Could not update patient')
            return
          } finally {
            setBusy(false)
          }
        }
      }
      setStep(2)
      return
    }
    if (!createAnyway) {
      setBusy(true)
      try {
        const matches = await checkDuplicatePatients({ full_name: fullName.trim(), patient_identifier: identifier.trim() || null })
        if (matches.length) {
          setDuplicates(matches)
          const ident = identifier.replace(/\s+/g, '').toUpperCase()
          setIdentifierClash(!!ident && matches.some((m) => (m.patient_identifier || '').replace(/\s+/g, '').toUpperCase() === ident))
          return
        }
      } catch (err) {
        toast.error(err instanceof ApiError ? err.message : 'Could not check for existing patients')
        return
      } finally {
        setBusy(false)
      }
    }
    setStep(2)
  }

  const submit = async () => {
    if (!approved || !studyValid || !patientValid) return
    setBusy(true)
    try {
      const report = await finalizeDraft(draftId, {
        selected_variant: variant.type,
        patient_id: existing?.id ?? null,
        new_patient: existing ? null : {
          full_name: fullName.trim(), patient_identifier: identifier.trim() || null, gender: gender as Gender,
        },
        create_new_anyway: createAnyway,
        age_value: ageNumber,
        age_unit: ageUnit,
        study_date: studyDate,
        exam: { modality, region: region.trim(), laterality } as ExamInfo,
        flag_acknowledgements: Object.entries(flagAcks).map(([i, at]) => ({ index: Number(i), acknowledged_at: at })),
        approved,
      })
      toast.success('Report finalized')
      onFinalized(report)
    } catch (err) {
      if (err instanceof ApiError && err.status === 409 && err.detail && typeof err.detail === 'object') {
        const d = err.detail as DuplicateDetail
        setDuplicates(d.matches)
        setIdentifierClash(d.code === 'identifier_in_use')
        setCreateAnyway(false)
        setStep(1)
        toast.error(d.message)
      } else {
        toast.error(err instanceof ApiError ? err.message : 'Could not finalize')
      }
    } finally {
      setBusy(false)
    }
  }

  const locked = !!existing && !unlocked

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-3" role="dialog" aria-modal="true" aria-labelledby="finalize-title">
      <div className="w-full max-w-2xl max-h-[92vh] overflow-auto rounded-2xl bg-white shadow-2xl">
        <header className="sticky top-0 bg-white border-b border-slate-200 px-5 py-4 flex items-center justify-between">
          <div>
            <h2 id="finalize-title" className="m-0 text-lg font-bold text-slate-900">Mark as final</h2>
            <p className="m-0 text-xs text-slate-500">Step {step} of 3 · {['Patient', 'This study', 'Confirm'][step - 1]}</p>
          </div>
          <button type="button" onClick={onClose} className="text-slate-500 hover:text-slate-900 bg-transparent border-0 text-2xl cursor-pointer" aria-label="Close">×</button>
        </header>

        <div className="p-5 space-y-4">
          {step === 1 && (
            <>
              {!existing && <PatientSearch onSelect={selectExisting} autoFocus />}
              {existing && (
                <div className="flex items-center justify-between rounded-lg bg-teal-50 border border-teal-200 px-3 py-2 text-sm">
                  <span>Existing patient selected{existing.latest_study_date ? ` · last study ${formatStudyDate(existing.latest_study_date)}` : ''}</span>
                  <span className="flex gap-3">
                    {!unlocked && <button type="button" className="text-teal-800 underline bg-transparent border-0 cursor-pointer" onClick={() => setUnlocked(true)}>Edit patient details</button>}
                    <button type="button" className="text-slate-600 underline bg-transparent border-0 cursor-pointer" onClick={clearExisting}>Change</button>
                  </span>
                </div>
              )}
              {!existing && <p className="text-xs text-slate-500 m-0">Or enter a new patient:</p>}

              <div>
                <label className={fieldLabel} htmlFor="fz-name">Full name *</label>
                <input id="fz-name" className="form-control w-full" value={fullName} maxLength={100} disabled={locked}
                  onChange={(e) => { setFullName(e.target.value); setDuplicates(null); setCreateAnyway(false) }} />
                {fullName && !nameValid && <p className="text-xs text-red-600 mt-1 mb-0">2–100 characters</p>}
              </div>
              <div>
                <label className={fieldLabel} htmlFor="fz-id">Patient ID / MRN</label>
                <input id="fz-id" className="form-control w-full" value={identifier} maxLength={64} disabled={locked}
                  onChange={(e) => { setIdentifier(e.target.value); setDuplicates(null); setCreateAnyway(false) }} />
                <p className="text-xs text-slate-500 mt-1 mb-0">Adding an ID makes comparisons reliable.</p>
              </div>
              <div>
                <span className={fieldLabel}>Gender *</span>
                <Segmented value={gender} options={GENDERS} onChange={setGender} disabled={locked} />
              </div>

              {duplicates && duplicates.length > 0 && !createAnyway && (
                <div className="rounded-xl border border-amber-300 bg-amber-50 p-4">
                  <h3 className="m-0 mb-2 text-sm font-bold text-amber-900">
                    {identifierClash ? 'A patient with this ID already exists' : 'Possible existing patient'}
                  </h3>
                  <ul className="list-none p-0 m-0 space-y-2">
                    {duplicates.map((m) => (
                      <li key={m.id} className="flex items-center justify-between gap-3 text-sm">
                        <span>
                          <strong>{m.full_name}</strong> · {m.patient_identifier ? `ID ${m.patient_identifier}` : 'No ID'} · {m.gender}
                          {m.latest_study_date ? ` · last ${formatStudyDate(m.latest_study_date)}` : ''}
                        </span>
                        <button type="button" className="btn btn-secondary text-xs py-1 px-3" onClick={() => selectExisting(m)}>Use this patient</button>
                      </li>
                    ))}
                  </ul>
                  {identifierClash ? (
                    <p className="text-xs text-amber-900 mt-3 mb-0">Patient IDs must be unique. Use the existing patient or change the ID.</p>
                  ) : (
                    <button type="button" className="mt-3 text-sm text-amber-900 underline bg-transparent border-0 cursor-pointer"
                      onClick={() => { setCreateAnyway(true); setStep(2) }}>
                      Create new anyway
                    </button>
                  )}
                </div>
              )}
            </>
          )}

          {step === 2 && (
            <>
              <div className="grid sm:grid-cols-2 gap-4">
                <div>
                  <label className={fieldLabel} htmlFor="fz-date">Study date *</label>
                  <input id="fz-date" type="date" className="form-control w-full" value={studyDate} max={today}
                    onChange={(e) => setStudyDate(e.target.value)} />
                  {dateError && <p className="text-xs text-red-600 mt-1 mb-0">{dateError}</p>}
                </div>
                <div>
                  <label className={fieldLabel} htmlFor="fz-age">{isObstetric ? 'Patient age (mother) *' : 'Age at study *'}</label>
                  <div className="flex gap-2">
                    <input id="fz-age" type="number" min={0} inputMode="numeric" className="form-control w-24" value={ageValue}
                      onChange={(e) => { setAgeValue(e.target.value); setAgeTouched(true) }} />
                    <select className="form-control" value={ageUnit} onChange={(e) => { setAgeUnit(e.target.value as AgeUnit); setAgeTouched(true) }}>
                      {AGE_UNITS.map((u) => <option key={u} value={u}>{u}</option>)}
                    </select>
                  </div>
                  {ageValue !== '' && ageError && <p className="text-xs text-red-600 mt-1 mb-0">{ageError}</p>}
                  {existing && !ageTouched && ageValue && <p className="text-xs text-slate-500 mt-1 mb-0">Pre-filled from the last report; check it.</p>}
                </div>
              </div>
              <div className="grid sm:grid-cols-3 gap-4">
                <div>
                  <label className={fieldLabel} htmlFor="fz-mod">Modality *</label>
                  <select id="fz-mod" className={`form-control w-full ${modality === 'UNSPECIFIED' ? 'border-amber-400 bg-amber-50' : ''}`}
                    value={modality} onChange={(e) => setModality(e.target.value as ExamInfo['modality'])}>
                    {MODALITIES.map((m) => <option key={m} value={m}>{m === 'UNSPECIFIED' ? 'Choose…' : m}</option>)}
                  </select>
                  {modality === 'UNSPECIFIED' && <p className="text-xs text-amber-700 mt-1 mb-0">The input did not state a modality. Choose one.</p>}
                </div>
                <div>
                  <label className={fieldLabel} htmlFor="fz-region">Region *</label>
                  <input id="fz-region" className="form-control w-full" value={region} maxLength={120} onChange={(e) => setRegion(e.target.value)} />
                </div>
                <div>
                  <label className={fieldLabel} htmlFor="fz-lat">Laterality</label>
                  <select id="fz-lat" className="form-control w-full" value={laterality} onChange={(e) => setLaterality(e.target.value)}>
                    {LATERALITIES.map((l) => <option key={l} value={l}>{l}</option>)}
                  </select>
                </div>
              </div>
            </>
          )}

          {step === 3 && (
            <>
              <div className="rounded-xl border border-slate-200 p-4">
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-sm border-b border-slate-200 pb-3 mb-3">
                  <div><span className="block text-xs text-slate-500">Patient</span><strong>{fullName.trim()}</strong></div>
                  <div><span className="block text-xs text-slate-500">ID</span>{identifier.trim() || '—'}</div>
                  <div><span className="block text-xs text-slate-500">{isObstetric ? 'Age (mother) / Gender' : 'Age / Gender'}</span>{ageNumber} {ageUnit} · {gender}</div>
                  <div><span className="block text-xs text-slate-500">Study date</span>{formatStudyDate(studyDate)}</div>
                </div>
                <ReportDocument text={variant.full_report} title={variant.title} reportFormat={reportFormat} showTitle />
              </div>
              <label className="flex items-start gap-2 text-sm cursor-pointer">
                <input type="checkbox" className="mt-1" checked={approved} onChange={(e) => setApproved(e.target.checked)} />
                <span>I have reviewed this report and approve it as final.</span>
              </label>
            </>
          )}
        </div>

        <footer className="sticky bottom-0 bg-white border-t border-slate-200 px-5 py-3 flex justify-between gap-3">
          <button type="button" className="btn btn-secondary py-2 px-4" disabled={busy}
            onClick={() => (step === 1 ? onClose() : setStep((s) => (s - 1) as Step))}>
            {step === 1 ? 'Cancel' : 'Back'}
          </button>
          {step === 1 && (
            <button type="button" className="btn btn-primary py-2 px-4 disabled:opacity-50" disabled={!patientValid || busy || (identifierClash && !!duplicates?.length)} onClick={goToStudy}>
              {busy ? 'Checking…' : 'Next'}
            </button>
          )}
          {step === 2 && (
            <button type="button" className="btn btn-primary py-2 px-4 disabled:opacity-50" disabled={!studyValid} onClick={() => setStep(3)}>Next</button>
          )}
          {step === 3 && (
            <button type="button" className="btn btn-primary py-2 px-4 disabled:opacity-50" disabled={!approved || busy} onClick={submit}>
              {busy ? 'Finalizing…' : 'Finalize report'}
            </button>
          )}
        </footer>
      </div>
    </div>
  )
}
