import { useState } from 'react'
import { ArrowLeft, ArrowRight, Settings, Loader2 } from 'lucide-react'
import { api } from '../../../services/api'
import { useToast } from '../../../contexts/ToastContext'
import type { ReelsState } from '../ReelsCutterPage'

interface Props {
  state: ReelsState
  update: (patch: Partial<ReelsState>) => void
  onNext: () => void
  onBack: () => void
}

const CHANNELS = [
  { value: 'devocional_com_jesus', label: 'Devocional com Jesus' },
  { value: 'hacker_patriota',      label: 'Hacker Patriota' },
  { value: 'broke_to_millionaire', label: 'Broke to Millionaire' },
]

export default function StepConfig({ state, update, onNext, onBack }: Props) {
  const toast = useToast()
  const [loading, setLoading] = useState(false)
  const [errorLog, setErrorLog] = useState('')
  const cfg = state.config

  function set(field: string) {
    return (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
      const val = e.target.type === 'number' ? Number(e.target.value) : e.target.value
      update({ config: { ...cfg, [field]: val } })
    }
  }

  async function handleProcess() {
    setLoading(true)
    try {
      const r = await api.post('/reelscutter/process', {
        url: state.url,
        video_id: state.video_id,
        transcription_text: state.transcription_text,
        config: cfg,
      })
      const clips = r.data.clips.map((c: any, i: number) => ({ ...c, clip_number: i + 1 }))
      update({ audio_path: r.data.audio_path, clips, selected_clips: clips })
      onNext()
    } catch (err: any) {
      const msg = err?.response?.data?.error || err.message || 'Erro desconhecido.'
      setErrorLog(msg)
      toast.error('Erro ao processar. Veja o log abaixo.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="max-w-lg mx-auto">
      <div className="flex items-center gap-3 mb-6">
        <div className="w-10 h-10 rounded-lg bg-navy-800 flex items-center justify-center">
          <Settings size={18} className="text-navy-300" />
        </div>
        <div>
          <h2 className="text-base font-semibold text-white">Configurações do pipeline</h2>
          <p className="text-xs text-navy-400">Ajuste os parâmetros antes de processar</p>
        </div>
      </div>

      <div className="space-y-5">
        {/* Channel */}
        <div>
          <label className="block text-xs font-medium text-navy-300 mb-1.5">Canal</label>
          <select value={cfg.channel_name} onChange={set('channel_name')} className="w-full border border-navy-700 rounded-lg px-3 py-2.5 text-sm text-white focus:outline-none focus:border-navy-500" style={{ background: '#0d1117' }}>
            {CHANNELS.map(c => <option key={c.value} value={c.value}>{c.label}</option>)}
          </select>
        </div>

        {/* Duracao */}
        <div>
          <label className="block text-xs font-medium text-navy-300 mb-1.5">Duração do clip (segundos)</label>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-navy-500 mb-1">Mínimo</label>
              <input type="number" value={cfg.min_duration} onChange={set('min_duration')} min={10} max={300} className="w-full border border-navy-700 rounded-lg px-3 py-2.5 text-sm text-white focus:outline-none focus:border-navy-500" style={{ background: '#0d1117' }} />
            </div>
            <div>
              <label className="block text-xs text-navy-500 mb-1">Máximo</label>
              <input type="number" value={cfg.max_duration} onChange={set('max_duration')} min={10} max={300} className="w-full border border-navy-700 rounded-lg px-3 py-2.5 text-sm text-white focus:outline-none focus:border-navy-500" style={{ background: '#0d1117' }} />
            </div>
          </div>
        </div>

        {/* Palavras por cena */}
        <div>
          <label className="block text-xs font-medium text-navy-300 mb-1.5">Palavras por cena (legenda)</label>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-navy-500 mb-1">Mínimo</label>
              <input type="number" value={cfg.min_words} onChange={set('min_words')} min={1} max={50} className="w-full border border-navy-700 rounded-lg px-3 py-2.5 text-sm text-white focus:outline-none focus:border-navy-500" style={{ background: '#0d1117' }} />
            </div>
            <div>
              <label className="block text-xs text-navy-500 mb-1">Máximo</label>
              <input type="number" value={cfg.max_words} onChange={set('max_words')} min={1} max={50} className="w-full border border-navy-700 rounded-lg px-3 py-2.5 text-sm text-white focus:outline-none focus:border-navy-500" style={{ background: '#0d1117' }} />
            </div>
          </div>
        </div>
      </div>

      <div className="flex items-center justify-between mt-8">
        <button onClick={onBack} disabled={loading} className="flex items-center gap-2 px-5 py-3 text-sm text-navy-400 hover:text-white border border-navy-700 hover:border-navy-500 rounded-lg transition-colors disabled:opacity-50">
          <ArrowLeft size={15} /> Voltar
        </button>
        <button onClick={handleProcess} disabled={loading} className="flex items-center gap-2 px-6 py-3 bg-navy-600 hover:bg-navy-500 disabled:opacity-50 text-white text-sm font-semibold rounded-lg transition-colors">
          {loading ? (
            <><Loader2 size={15} className="animate-spin" /> Baixando áudio e analisando...</>
          ) : (
            <>Processar <ArrowRight size={15} /></>
          )}
        </button>
      </div>

      {loading && (
        <p className="text-xs text-navy-500 text-center mt-3">
          Isso pode levar alguns minutos — baixando o áudio e enviando para o Gemini...
        </p>
      )}

      {errorLog && !loading && (
        <div className="mt-4 rounded-lg border border-red-900 p-3" style={{ background: '#1a0a0a' }}>
          <p className="text-xs font-medium text-red-400 mb-1">Log de erro:</p>
          <pre className="text-xs text-red-300 whitespace-pre-wrap break-all max-h-40 overflow-y-auto">{errorLog}</pre>
        </div>
      )}
    </div>
  )
}
