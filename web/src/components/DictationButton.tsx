import { useEffect, useRef, useState } from 'react'
import toast from 'react-hot-toast'
import { transcribeAudio } from '../api/reports'
import { ApiError } from '../api/client'

interface DictationButtonProps {
  value: string
  onUpdate: (next: string) => void
  compact?: boolean
}

async function getAudioStream(): Promise<MediaStream> {
  try {
    return await navigator.mediaDevices.getUserMedia({ audio: true })
  } catch (err: unknown) {
    const error = err as { name?: string }
    if (error.name !== 'NotFoundError' && error.name !== 'DevicesNotFoundError') throw err
  }
  const devices = await navigator.mediaDevices.enumerateDevices()
  for (const dev of devices.filter((d) => d.kind === 'audioinput')) {
    if (!dev.deviceId) continue
    try {
      return await navigator.mediaDevices.getUserMedia({ audio: { deviceId: { exact: dev.deviceId } } })
    } catch {
      // try next device
    }
  }
  return navigator.mediaDevices.getUserMedia({ audio: { deviceId: 'default' } })
}

export function DictationButton({ value, onUpdate, compact = false }: DictationButtonProps) {
  const [recording, setRecording] = useState(false)
  const [busy, setBusy] = useState(false)
  const [seconds, setSeconds] = useState(0)
  const recorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const timerRef = useRef<number | null>(null)

  useEffect(() => {
    return () => {
      if (timerRef.current) window.clearInterval(timerRef.current)
      if (recorderRef.current && recorderRef.current.state !== 'inactive') recorderRef.current.stop()
    }
  }, [])

  const stop = () => {
    if (timerRef.current) {
      window.clearInterval(timerRef.current)
      timerRef.current = null
    }
    if (recorderRef.current && recorderRef.current.state !== 'inactive') {
      recorderRef.current.stop()
      recorderRef.current = null
    }
    setRecording(false)
  }

  const toggle = async () => {
    if (recording) {
      stop()
      return
    }
    if (!navigator.mediaDevices?.getUserMedia) {
      toast.error('Microphone needs HTTPS or localhost')
      return
    }
    try {
      const stream = await getAudioStream()
      const mime = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4'].find((t) => MediaRecorder.isTypeSupported(t)) || ''
      const recorder = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream)
      chunksRef.current = []
      recorder.ondataavailable = (event) => {
        if (event.data?.size) chunksRef.current.push(event.data)
      }
      recorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop())
        const blob = new Blob(chunksRef.current, { type: mime || 'audio/webm' })
        if (!blob.size) {
          toast.error('No audio captured')
          return
        }
        setBusy(true)
        const toastId = toast.loading('Transcribing dictation…')
        try {
          const res = await transcribeAudio(blob, 'dictation.webm')
          const spoken = res.text?.trim()
          if (spoken) {
            onUpdate(value.trim() ? `${value.trim()} ${spoken}` : spoken)
            toast.success('Dictation added to the prompt', { id: toastId })
          } else {
            toast('No clear speech detected', { id: toastId, icon: 'ℹ️' })
          }
        } catch (err) {
          toast.error(err instanceof ApiError ? err.message : 'Transcription failed', { id: toastId })
        } finally {
          setBusy(false)
        }
      }
      recorder.start(400)
      recorderRef.current = recorder
      setRecording(true)
      setSeconds(0)
      timerRef.current = window.setInterval(() => setSeconds((s) => s + 1), 1000)
      toast('Listening… click the mic again to stop', { icon: '🎙️' })
    } catch (err: unknown) {
      const name = (err as { name?: string }).name
      if (name === 'NotAllowedError') toast.error('Microphone permission denied')
      else if (name === 'NotFoundError') toast.error('No microphone found')
      else toast.error('Could not start dictation')
    }
  }

  const label = recording
    ? `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`
    : busy
      ? '…'
      : 'Dictate'

  return (
    <button
      type="button"
      className={`dictate-btn ${recording ? 'is-live' : ''} ${compact ? 'is-compact' : ''}`}
      onClick={toggle}
      disabled={busy}
      aria-pressed={recording}
      title={recording ? 'Stop dictation' : 'Dictate the prompt'}
    >
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M12 14a3 3 0 0 0 3-3V6a3 3 0 1 0-6 0v5a3 3 0 0 0 3 3Zm5-3a5 5 0 0 1-10 0H5a7 7 0 0 0 6 6.92V20H9v2h6v-2h-2v-2.08A7 7 0 0 0 19 11h-2Z" />
      </svg>
      {!compact && <span>{label}</span>}
      {compact && recording && <span className="dictate-timer">{label}</span>}
    </button>
  )
}
