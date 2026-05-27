import { useState } from 'react'
import { X } from 'lucide-react'
import type { ClipData } from './ClipEditModal'
import type { ReelsState } from '../ReelsCutterPage'

interface Props {
  transcript: ReelsState['transcript']
  nextClipNumber: number
  onSave: (clip: ClipData) => void
  onClose: () => void
}

function fmt(s: number) {
  const m = Math.floor(s / 60)
  const ss = Math.floor(s % 60)
  return `${String(m).padStart(2, '0')}:${String(ss).padStart(2, '0')}`
}

const CATEGORIES = [
  'revelacao', 'confronto', 'promessa', 'historia', 'declaracao', 'chamado',
]

export default function ClipFormModal({ transcript, nextClipNumber, onSave, onClose }: Props) {
  const [title,    setTitle]    = useState('')
  const [hook,     setHook]     = useState('')
  const [whyViral, setWhyViral] = useState('')
  const [category, setCategory] = useState('')
  const [selected, setSelected] = useState<number[]>([])

  function toggleSeg(i: number) {
    setSelected(prev =>
      prev.includes(i) ? prev.filter(x => x !== i) : [...prev, i]
    )
  }

  function handleSave() {
    if (!title.trim() || selected.length === 0) return
    const sorted = [...selected].sort((a, b) => a - b)
    const first  = transcript[sorted[0]]
    const last   = transcript[sorted[sorted.length - 1]]
    const start  = first.start
    const end    = last.start + last.duration

    onSave({
      clip_number:      nextClipNumber,
      title:            title.trim(),
      hook:             hook.trim() || undefined,
      why_viral:        whyViral.trim() || undefined,
      category:         category || undefined,
      start_time:       start,
      end_time:         end,
      duration_seconds: end - start,
      visibleIndexes:   sorted,
    })
    onClose()
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: 'rgba(0,0,0,0.75)' }}
      onMouseDown={e => { if (e.target === e.currentTarget) onClose() }}
    >
      <div
        className="relative w-full max-w-2xl rounded-2xl border border-navy-700 flex flex-col"
        style={{ background: '#0f1623', maxHeight: '90vh' }}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-navy-800 shrink-0">
          <h2 className="text-white font-semibold text-base">Novo corte manual</h2>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-navy-500 hover:text-white hover:bg-navy-800 transition-colors"
          >
            <X size={18} />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto rc-scroll px-6 py-4 space-y-4">
          {/* Título */}
          <div>
            <label className="block text-xs text-navy-400 mb-1">Título *</label>
            <input
              value={title}
              onChange={e => setTitle(e.target.value)}
              placeholder="Nome do clip"
              className="w-full rounded-lg border border-navy-700 bg-navy-900 text-white text-sm px-3 py-2 focus:outline-none focus:border-navy-500"
            />
          </div>

          {/* Categoria */}
          <div>
            <label className="block text-xs text-navy-400 mb-1">Categoria</label>
            <div className="flex flex-wrap gap-2">
              {CATEGORIES.map(c => (
                <button
                  key={c}
                  onClick={() => setCategory(cat => cat === c ? '' : c)}
                  className={`text-xs px-3 py-1 rounded-full border transition-colors ${
                    category === c
                      ? 'border-navy-500 bg-navy-700 text-white'
                      : 'border-navy-700 text-navy-500 hover:border-navy-600 hover:text-navy-300'
                  }`}
                >
                  {c}
                </button>
              ))}
            </div>
          </div>

          {/* Hook */}
          <div>
            <label className="block text-xs text-navy-400 mb-1">Hook (frase de abertura)</label>
            <input
              value={hook}
              onChange={e => setHook(e.target.value)}
              placeholder="Primeira frase impactante..."
              className="w-full rounded-lg border border-navy-700 bg-navy-900 text-white text-sm px-3 py-2 focus:outline-none focus:border-navy-500"
            />
          </div>

          {/* Why viral */}
          <div>
            <label className="block text-xs text-navy-400 mb-1">Por que vai viralizar?</label>
            <input
              value={whyViral}
              onChange={e => setWhyViral(e.target.value)}
              placeholder="Motivo do potencial viral..."
              className="w-full rounded-lg border border-navy-700 bg-navy-900 text-white text-sm px-3 py-2 focus:outline-none focus:border-navy-500"
            />
          </div>

          {/* Selecionar segmentos */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="text-xs text-navy-400">
                Selecione os segmentos do clip *{' '}
                <span className="text-navy-600">({selected.length} selecionados)</span>
              </label>
              {selected.length > 0 && (
                <button
                  onClick={() => setSelected([])}
                  className="text-xs text-navy-600 hover:text-navy-400 transition-colors"
                >
                  Limpar
                </button>
              )}
            </div>
            <div className="rounded-lg border border-navy-800 overflow-hidden">
              <div className="overflow-y-auto rc-scroll" style={{ maxHeight: '240px' }}>
                {transcript.map((seg, i) => (
                  <div
                    key={i}
                    onClick={() => toggleSeg(i)}
                    className={`flex items-start gap-3 px-3 py-2 cursor-pointer transition-colors ${
                      selected.includes(i)
                        ? 'bg-navy-800'
                        : 'hover:bg-navy-900'
                    }`}
                  >
                    <div className={`mt-0.5 w-4 h-4 rounded border shrink-0 flex items-center justify-center ${
                      selected.includes(i) ? 'bg-navy-500 border-navy-500' : 'border-navy-700'
                    }`}>
                      {selected.includes(i) && <div className="w-2 h-2 rounded-sm bg-white" />}
                    </div>
                    <span className="text-[10px] text-navy-600 font-mono shrink-0 mt-0.5 w-10">
                      {fmt(seg.start)}
                    </span>
                    <span className={`text-sm leading-relaxed ${selected.includes(i) ? 'text-navy-200' : 'text-navy-500'}`}>
                      {seg.text}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-6 py-4 border-t border-navy-800 shrink-0">
          <p className="text-xs text-navy-600">
            {selected.length > 0
              ? `${fmt(transcript[[...selected].sort((a,b)=>a-b)[0]].start)} → ${fmt(transcript[[...selected].sort((a,b)=>a-b)[selected.length-1]].start + transcript[[...selected].sort((a,b)=>a-b)[selected.length-1]].duration)}`
              : 'Nenhum segmento selecionado'
            }
          </p>
          <div className="flex items-center gap-3">
            <button
              onClick={onClose}
              className="px-5 py-2.5 text-sm text-navy-400 hover:text-white border border-navy-700 hover:border-navy-500 rounded-lg transition-colors"
            >
              Cancelar
            </button>
            <button
              onClick={handleSave}
              disabled={!title.trim() || selected.length === 0}
              className="px-6 py-2.5 text-sm font-semibold bg-navy-600 hover:bg-navy-500 disabled:opacity-40 disabled:cursor-not-allowed text-white rounded-lg transition-colors"
            >
              Criar corte
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
