import { ArrowLeft, ArrowRight, FileText } from 'lucide-react'
import type { ReelsState } from '../ReelsCutterPage'

interface Props {
  state: ReelsState
  onNext: () => void
  onBack: () => void
}

function formatTime(seconds: number) {
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

export default function StepTranscript({ state, onNext, onBack }: Props) {
  const totalDuration = state.transcript.length > 0
    ? state.transcript[state.transcript.length - 1].start + state.transcript[state.transcript.length - 1].duration
    : 0

  return (
    <div>
      <div className="flex items-center gap-3 mb-6">
        <div className="w-10 h-10 rounded-lg bg-navy-800 flex items-center justify-center">
          <FileText size={18} className="text-navy-300" />
        </div>
        <div>
          <h2 className="text-base font-semibold text-white">Transcrição encontrada</h2>
          <p className="text-xs text-navy-400">
            {state.transcript.length} segmentos · {formatTime(totalDuration)} de duração · Video ID: <span className="font-mono">{state.video_id}</span>
          </p>
        </div>
      </div>

      <div
        className="rounded-lg border border-navy-800 p-4 h-80 overflow-y-auto text-sm space-y-1 mb-6 font-mono"
        style={{ background: '#0d1117' }}
      >
        {state.transcript.map((seg, i) => (
          <div key={i} className="flex gap-3 hover:bg-navy-900 px-2 py-0.5 rounded">
            <span className="text-navy-600 shrink-0 w-12">{formatTime(seg.start)}</span>
            <span className="text-navy-200">{seg.text}</span>
          </div>
        ))}
      </div>

      <div className="flex items-center justify-between">
        <button onClick={onBack} className="flex items-center gap-2 px-5 py-3 text-sm text-navy-400 hover:text-white border border-navy-700 hover:border-navy-500 rounded-lg transition-colors">
          <ArrowLeft size={15} /> Voltar
        </button>
        <div className="flex items-center gap-3">
          <p className="text-xs text-navy-500">Este vídeo tem potencial? Continua?</p>
          <button onClick={onNext} className="flex items-center gap-2 px-6 py-3 bg-navy-600 hover:bg-navy-500 text-white text-sm font-semibold rounded-lg transition-colors">
            Continuar <ArrowRight size={15} />
          </button>
        </div>
      </div>
    </div>
  )
}
