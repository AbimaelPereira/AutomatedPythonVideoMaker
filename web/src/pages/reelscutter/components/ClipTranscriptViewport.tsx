'use client'

import { useRef } from 'react'
import {
  SkipBack, SkipForward, ChevronLeft, ChevronRight,
  Undo2, Scissors,
} from 'lucide-react'

export interface TranscriptSeg {
  text: string
  start: number
  duration: number
}

interface SegmentState extends TranscriptSeg {
  index: number
  hide: boolean
  isOriginal: boolean
}

interface Props {
  transcript: TranscriptSeg[]
  startTime: number
  endTime: number
  // segmentos visíveis correntes (índices)
  visibleIndexes: number[]
  onChange: (visibleIndexes: number[], newStart: number, newEnd: number) => void
}

function formatTime(s: number) {
  const m = Math.floor(s / 60)
  const ss = Math.floor(s % 60)
  return `${String(m).padStart(2, '0')}:${String(ss).padStart(2, '0')}`
}

const STEP = 5

export default function ClipTranscriptViewport({ transcript, visibleIndexes, onChange }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)

  // Monta a lista de segmentos com estado
  const segs: SegmentState[] = transcript.map((s, i) => ({
    ...s,
    index: i,
    hide: !visibleIndexes.includes(i),
    isOriginal: false,
  }))

  const visibleSegs = segs.filter(s => !s.hide)
  const firstVisIdx = visibleSegs.length > 0 ? visibleSegs[0].index : -1
  const lastVisIdx  = visibleSegs.length > 0 ? visibleSegs[visibleSegs.length - 1].index : -1

  const hasBefore = firstVisIdx > 0
  const hasAfter  = lastVisIdx < transcript.length - 1

  function commit(newVisible: number[]) {
    if (newVisible.length === 0) return
    const sorted = [...newVisible].sort((a, b) => a - b)
    const first  = transcript[sorted[0]]
    const last   = transcript[sorted[sorted.length - 1]]
    onChange(sorted, first.start, last.start + last.duration)
  }

  function expandInicio() {
    let added = 0
    const next = [...visibleIndexes]
    for (let i = firstVisIdx - 1; i >= 0 && added < STEP; i--) {
      next.push(i)
      added++
    }
    commit(next)
  }

  function expandFim() {
    let added = 0
    const next = [...visibleIndexes]
    for (let i = lastVisIdx + 1; i < transcript.length && added < STEP; i++) {
      next.push(i)
      added++
    }
    commit(next)
  }

  function recolherInicio() {
    let removed = 0
    let next = [...visibleIndexes].sort((a, b) => a - b)
    while (removed < STEP && next.length > 1) {
      next.shift()
      removed++
    }
    commit(next)
  }

  function recolherFim() {
    let removed = 0
    let next = [...visibleIndexes].sort((a, b) => a - b)
    while (removed < STEP && next.length > 1) {
      next.pop()
      removed++
    }
    commit(next)
  }

  function irInicio() {
    const next = Array.from({ length: transcript.length }, (_, i) => i)
      .filter(i => i <= lastVisIdx)
    commit(next)
  }

  function irFim() {
    const next = Array.from({ length: transcript.length }, (_, i) => i)
      .filter(i => i >= firstVisIdx)
    commit(next)
  }

  function handleCut() {
    const sel = window.getSelection()
    if (!sel || sel.isCollapsed || sel.rangeCount === 0) return
    const range = sel.getRangeAt(0)
    const container = containerRef.current
    if (!container) return

    let idxStart: number | null = null
    let idxEnd: number | null = null

    container.querySelectorAll<HTMLElement>('[data-seg-index]').forEach(el => {
      const idx = parseInt(el.dataset.segIndex!)
      const intersects = range.intersectsNode(el)
      if (intersects) {
        if (idxStart === null || idx < idxStart) idxStart = idx
        if (idxEnd === null || idx > idxEnd) idxEnd = idx
      }
    })

    if (idxStart === null || idxEnd === null) return

    const next: number[] = []
    for (let i = idxStart; i <= idxEnd; i++) next.push(i)
    commit(next)
    sel.removeAllRanges()
  }

  const firstSeg = visibleSegs[0]
  const lastSeg  = visibleSegs[visibleSegs.length - 1]

  return (
    <div className="mt-3 rounded-lg border border-navy-700" style={{ background: '#0d1117' }}>
      {/* ── Cabeçalho início ── */}
      <div className="flex items-center gap-1 px-3 py-2 border-b border-navy-800">
        {hasBefore && (
          <>
            <IconBtn onClick={irInicio} tip="Ir ao início"><SkipBack size={13} /></IconBtn>
            <IconBtn onClick={expandInicio} tip="Expandir início"><ChevronLeft size={13} /></IconBtn>
          </>
        )}
        {visibleSegs.length > 1 && (
          <IconBtn onClick={recolherInicio} tip="Recolher início" danger><ChevronRight size={13} /></IconBtn>
        )}
        {firstSeg && (
          <span className="ml-2 text-xs text-navy-500 font-mono">[{formatTime(firstSeg.start)}]</span>
        )}
      </div>

      {/* ── Segmentos ── */}
      <div
        ref={containerRef}
        className="px-3 py-2 text-sm leading-relaxed text-navy-200 select-text cursor-text"
      >
        {segs.map(seg => !seg.hide && (
          <span
            key={seg.index}
            data-seg-index={seg.index}
            className="inline"
          >
            {seg.text}{' '}
          </span>
        ))}
      </div>

      {/* ── Rodapé fim ── */}
      <div className="flex items-center gap-1 px-3 py-2 border-t border-navy-800">
        {lastSeg && (
          <span className="text-xs text-navy-500 font-mono mr-2">[{formatTime(lastSeg.start + lastSeg.duration)}]</span>
        )}
        {visibleSegs.length > 1 && (
          <IconBtn onClick={recolherFim} tip="Recolher fim" danger><ChevronLeft size={13} /></IconBtn>
        )}
        {hasAfter && (
          <>
            <IconBtn onClick={expandFim} tip="Expandir fim"><ChevronRight size={13} /></IconBtn>
            <IconBtn onClick={irFim} tip="Ir ao fim"><SkipForward size={13} /></IconBtn>
          </>
        )}
        {/* Recortar por seleção */}
        <button
          onClick={handleCut}
          title="Recortar seleção"
          className="ml-auto flex items-center gap-1 text-xs text-red-400 hover:text-red-300 px-2 py-1 rounded hover:bg-navy-800 transition-colors"
        >
          <Scissors size={12} /> Recortar seleção
        </button>
      </div>
    </div>
  )
}

function IconBtn({ children, onClick, tip, danger }: {
  children: React.ReactNode
  onClick: () => void
  tip?: string
  danger?: boolean
}) {
  return (
    <button
      onClick={onClick}
      title={tip}
      className={`p-1.5 rounded hover:bg-navy-800 transition-colors ${danger ? 'text-red-400 hover:text-red-300' : 'text-navy-400 hover:text-white'}`}
    >
      {children}
    </button>
  )
}
