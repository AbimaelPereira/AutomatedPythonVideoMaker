import { useState, useEffect, useRef, useCallback } from 'react'
import { X, RotateCcw, Play, Pause, Check } from 'lucide-react'
import { useAudioPlayer } from '../hooks/useAudioPlayer'
import { useToast } from '../../../contexts/ToastContext'
import type { ReelsState } from '../ReelsCutterPage'

export interface ClipData {
  clip_number: number
  start_time: number
  end_time: number
  duration_seconds: number
  title: string
  hook?: string
  why_viral?: string
  category?: string
  scenes_text?: string[]
  visibleIndexes?: number[]
}

interface Props {
  clip: ClipData
  originalClip?: ClipData
  transcript: ReelsState['transcript']
  audioPath: string
  onSave: (updated: ClipData) => void
  onClose: () => void
}

const CATEGORY_COLORS: Record<string, string> = {
  revelacao:  'text-purple-400',
  confronto:  'text-orange-400',
  promessa:   'text-blue-400',
  historia:   'text-teal-400',
  declaracao: 'text-yellow-400',
  chamado:    'text-pink-400',
}

function fmt(s: number) {
  if (!isFinite(s) || s < 0) s = 0
  const m  = Math.floor(s / 60)
  const ss = Math.floor(s % 60)
  return `${String(m).padStart(2, '0')}:${String(ss).padStart(2, '0')}`
}

function initialIndexes(transcript: ReelsState['transcript'], start: number, end: number) {
  return transcript
    .map((s, i) => ({ ...s, i }))
    .filter(s => s.start < end + 0.5 && s.start + s.duration > start - 0.5)
    .map(s => s.i)
}

const BORDER = '1px solid #1e2229'

export default function ClipEditModal({ clip, originalClip, transcript, audioPath, onSave, onClose }: Props) {
  const toast = useToast()
  const { state: ps, play, pause, seek, seekAndPlay } = useAudioPlayer(audioPath)

  const [title,          setTitle]          = useState(clip.title)
  const [followClip,     setFollowClip]     = useState(true)
  const [visibleIndexes, setVisibleIndexes] = useState<number[]>(() =>
    clip.visibleIndexes?.length
      ? clip.visibleIndexes
      : initialIndexes(transcript, clip.start_time, clip.end_time)
  )
  const [segTexts, setSegTexts] = useState<Record<number, string>>(() => {
    const m: Record<number, string> = {}
    transcript.forEach((s, i) => { m[i] = s.text })
    return m
  })
  const [editingIdx, setEditingIdx] = useState<number | null>(null)

  const clipRange = useCallback(() => {
    if (visibleIndexes.length === 0) return { start: clip.start_time, end: clip.end_time }
    const sorted = [...visibleIndexes].sort((a, b) => a - b)
    const first  = transcript[sorted[0]]
    const last   = transcript[sorted[sorted.length - 1]]
    return { start: first.start, end: last.start + last.duration }
  }, [visibleIndexes, transcript, clip])

  // scroll automático
  const segRefs      = useRef<Record<number, HTMLDivElement | null>>({})
  const lastScrolled = useRef<number>(-1)

  useEffect(() => {
    if (!ps.playing) return
    let idx = -1
    for (let i = 0; i < transcript.length; i++) {
      if (transcript[i].start <= ps.currentTime) idx = i
      else break
    }
    if (idx !== -1 && idx !== lastScrolled.current) {
      lastScrolled.current = idx
      segRefs.current[idx]?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
    }
  }, [ps.currentTime, ps.playing, transcript])

  function toggleSegment(i: number) {
    setVisibleIndexes(prev =>
      prev.includes(i) ? prev.filter(x => x !== i) : [...prev, i]
    )
  }

  function handleRestoreGemini() {
    if (!originalClip) return
    setTitle(originalClip.title)
    setVisibleIndexes(
      originalClip.visibleIndexes?.length
        ? originalClip.visibleIndexes
        : initialIndexes(transcript, originalClip.start_time, originalClip.end_time)
    )
    toast.success('Sugestão do Gemini restaurada.')
  }

  function handleSave() {
    const r = clipRange()
    onSave({
      ...clip,
      title,
      start_time:       r.start,
      end_time:         r.end,
      duration_seconds: r.end - r.start,
      visibleIndexes,
    })
    onClose()
  }

  const range        = clipRange()
  const duration     = ps.duration || 1
  const clipStartPct = (range.start / duration) * 100
  const clipEndPct   = (range.end   / duration) * 100
  const currentPct   = Math.min(100, (ps.currentTime / duration) * 100)
  const inClip       = ps.currentTime >= range.start && ps.currentTime < range.end

  function handleBarClick(e: React.MouseEvent<HTMLDivElement>) {
    const rect = e.currentTarget.getBoundingClientRect()
    seek(Math.max(0, Math.min(duration, ((e.clientX - rect.left) / rect.width) * duration)))
  }

  let activeIdx = -1
  for (let i = 0; i < transcript.length; i++) {
    if (transcript[i].start <= ps.currentTime) activeIdx = i
    else break
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: 'rgba(0,0,0,0.78)' }}
      onMouseDown={e => { if (e.target === e.currentTarget) onClose() }}
    >
      <div
        className="relative w-full max-w-3xl rounded-2xl flex flex-col"
        style={{ background: '#13161b', border: '1px solid #222630', maxHeight: '92vh' }}
      >

        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 shrink-0" style={{ borderBottom: BORDER }}>
          <div className="flex-1 min-w-0 mr-4">
            <input
              value={title}
              onChange={e => setTitle(e.target.value)}
              className="w-full bg-transparent text-white font-semibold text-base focus:outline-none border-b border-transparent focus:border-navy-600 transition-colors pb-0.5"
              placeholder="Título do clip"
            />
            {clip.category && (
              <span className={`text-xs ${CATEGORY_COLORS[clip.category.split('|')[0]] ?? 'text-navy-500'}`}>
                {clip.category}
              </span>
            )}
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {originalClip && (
              <button
                onClick={handleRestoreGemini}
                className="flex items-center gap-1.5 text-xs text-navy-400 hover:text-white px-3 py-1.5 rounded-lg transition-colors"
                style={{ border: '1px solid #222630' }}
              >
                <RotateCcw size={12} /> Restaurar Gemini
              </button>
            )}
            <button
              onClick={onClose}
              className="p-1.5 rounded-lg text-navy-500 hover:text-white transition-colors"
              style={{ background: '#1a1e25' }}
            >
              <X size={18} />
            </button>
          </div>
        </div>

        {/* Sub-header */}
        <div className="px-6 py-2.5 shrink-0 flex items-center justify-between gap-4" style={{ borderBottom: BORDER }}>
          <p className="text-[11px] font-mono" style={{ color: '#4a5568' }}>
            {fmt(range.start)} → {fmt(range.end)}
            {' · '}{(range.end - range.start).toFixed(0)}s
            {' · '}{visibleIndexes.length} segmentos
          </p>

          <label className="flex items-center gap-2 cursor-pointer shrink-0 select-none">
            <span className="text-[11px]" style={{ color: '#4a5568' }}>Continua após segmento</span>
            <button
              role="switch"
              aria-checked={followClip}
              onClick={() => setFollowClip(v => !v)}
              className="relative w-9 h-5 rounded-full transition-colors"
              style={{ background: followClip ? '#2f4a8f' : '#1a1e25', border: '1px solid #222630' }}
            >
              <span
                className="absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-all duration-200"
                style={{ left: followClip ? 'calc(100% - 18px)' : '2px' }}
              />
            </button>
          </label>
        </div>

        {/* Transcript */}
        <div className="flex-1 overflow-y-auto rc-scroll px-2 py-2 min-h-0">
          {transcript.map((seg, i) => {
            const isActive   = i === activeIdx
            const isSelected = visibleIndexes.includes(i)
            const isEditing  = editingIdx === i

            return (
              <div
                key={i}
                ref={el => { segRefs.current[i] = el }}
                className="flex items-start gap-2 px-3 py-1.5 rounded-lg mb-0.5 transition-colors"
                style={{ background: isActive ? '#1a1e25' : undefined }}
              >
                {/* Checkbox seleção */}
                <button
                  onClick={() => toggleSegment(i)}
                  className="mt-0.5 w-4 h-4 rounded shrink-0 flex items-center justify-center transition-colors"
                  style={{
                    background: isSelected ? 'transparent' : 'transparent',
                    border: isSelected ? 'none' : '1px solid #2a2f38',
                  }}
                >
                  {isSelected
                    ? <Check size={13} color="#22c55e" strokeWidth={2.5} />
                    : null
                  }
                </button>

                {/* Botão de seek — move a agulha e retoma play se já estava tocando */}
                <button
                  onClick={() => seekAndPlay(seg.start)}
                  className="mt-0.5 shrink-0 p-0.5 rounded transition-colors"
                  style={{ color: isActive ? '#fff' : '#2a2f38' }}
                  onMouseEnter={e => { (e.currentTarget as HTMLElement).style.color = '#7890c2' }}
                  onMouseLeave={e => { (e.currentTarget as HTMLElement).style.color = isActive ? '#fff' : '#2a2f38' }}
                >
                  <Play size={12} />
                </button>

                {/* Tempo */}
                <span className="text-[10px] font-mono shrink-0 mt-0.5 w-10" style={{ color: '#2a3040' }}>
                  {fmt(seg.start)}
                </span>

                {/* Texto */}
                {isEditing ? (
                  <input
                    autoFocus
                    value={segTexts[i]}
                    onChange={e => setSegTexts(prev => ({ ...prev, [i]: e.target.value }))}
                    onBlur={() => setEditingIdx(null)}
                    onKeyDown={e => { if (e.key === 'Enter' || e.key === 'Escape') setEditingIdx(null) }}
                    className="flex-1 text-sm rounded px-2 py-0.5 text-white focus:outline-none"
                    style={{ background: '#0d1117', border: '1px solid #2f4a8f' }}
                  />
                ) : (
                  <span
                    onDoubleClick={() => setEditingIdx(i)}
                    title="Clique duplo para editar"
                    className="flex-1 text-sm leading-relaxed cursor-text"
                    style={{ color: isActive ? '#e8edf5' : isSelected ? '#9fb0d4' : '#374151' }}
                  >
                    {segTexts[i]}
                  </span>
                )}
              </div>
            )
          })}
        </div>

        {/* Player */}
        <div className="shrink-0 px-6 py-4" style={{ borderTop: BORDER }}>
          <div className="flex items-center gap-4">
            <button
              onClick={() => { if (ps.playing) pause(); else play() }}
              className="w-9 h-9 rounded-full flex items-center justify-center text-white transition-colors shrink-0"
              style={{ background: '#1a1e25', border: '1px solid #222630' }}
            >
              {ps.playing ? <Pause size={15} /> : <Play size={15} />}
            </button>

            <div className="flex-1 flex flex-col gap-1.5">
              <div className="flex justify-between text-[10px] font-mono" style={{ color: '#374151' }}>
                <span>{fmt(ps.currentTime)}</span>
                <span style={{ color: '#2a3040' }}>{fmt(range.start)} – {fmt(range.end)}</span>
                <span>{fmt(duration)}</span>
              </div>

              <div
                className="relative h-2 rounded-full cursor-pointer group"
                style={{ background: '#0d1117' }}
                onClick={handleBarClick}
              >
                {/* Faixa do clip */}
                <div
                  className="absolute inset-y-0 rounded-full"
                  style={{ left: `${clipStartPct}%`, width: `${clipEndPct - clipStartPct}%`, background: '#1a2540' }}
                />
                {/* Progresso */}
                <div
                  className="absolute inset-y-0 left-0 rounded-full"
                  style={{ width: `${currentPct}%`, background: inClip ? '#5a76b5' : '#1e2a40' }}
                />
                {/* Marcadores início/fim */}
                <div className="absolute top-1/2 -translate-y-1/2 w-px rounded-full"
                  style={{ left: `${clipStartPct}%`, height: '14px', background: '#3d5ca8' }} />
                <div className="absolute top-1/2 -translate-y-1/2 w-px rounded-full"
                  style={{ left: `${clipEndPct}%`, height: '14px', background: '#3d5ca8' }} />
                {/* Thumb */}
                <div
                  className="absolute top-1/2 -translate-y-1/2 w-3.5 h-3.5 rounded-full bg-white shadow-md opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none"
                  style={{ left: `calc(${currentPct}% - 7px)` }}
                />
              </div>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 px-6 py-4 shrink-0" style={{ borderTop: BORDER }}>
          <button
            onClick={onClose}
            className="px-5 py-2.5 text-sm rounded-lg transition-colors"
            style={{ color: '#4a5568', border: '1px solid #222630' }}
          >
            Cancelar
          </button>
          <button
            onClick={handleSave}
            className="px-6 py-2.5 text-sm font-semibold text-white rounded-lg transition-colors"
            style={{ background: '#2f4a8f' }}
          >
            Salvar corte
          </button>
        </div>

      </div>
    </div>
  )
}
