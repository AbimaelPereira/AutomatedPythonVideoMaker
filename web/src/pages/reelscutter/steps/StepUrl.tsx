import { useState } from 'react'
import { Link2, ArrowRight } from 'lucide-react'
import { api } from '../../../services/api'
import { useToast } from '../../../contexts/ToastContext'
import type { ReelsState } from '../ReelsCutterPage'

interface Props {
  state: ReelsState
  update: (patch: Partial<ReelsState>) => void
  onNext: () => void
}

export default function StepUrl({ state, update, onNext }: Props) {
  const toast = useToast()
  const [loading, setLoading] = useState(false)
  const [errorLog, setErrorLog] = useState('')

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!state.url.trim()) return
    setLoading(true)
    try {
      const r = await api.post('/reelscutter/transcript', { url: state.url })
      update({
        video_id: r.data.video_id,
        transcript: r.data.transcript,
        transcription_text: r.data.text,
      })
      onNext()
    } catch (err: any) {
      const msg = err?.response?.data?.error || err.message || 'Erro desconhecido.'
      setErrorLog(msg)
      toast.error('Erro ao buscar transcrição.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="max-w-xl mx-auto">
      <div className="flex items-center gap-3 mb-6">
        <div className="w-10 h-10 rounded-lg bg-navy-800 flex items-center justify-center">
          <Link2 size={18} className="text-navy-300" />
        </div>
        <div>
          <h2 className="text-base font-semibold text-white">Cole o link do vídeo</h2>
          <p className="text-xs text-navy-400">YouTube, Shorts ou qualquer link yt-dlp suportado</p>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        <input
          type="url"
          value={state.url}
          onChange={e => update({ url: e.target.value })}
          placeholder="https://www.youtube.com/watch?v=..."
          required
          className="w-full border border-navy-700 rounded-lg px-4 py-3 text-sm text-white placeholder-navy-500 focus:outline-none focus:border-navy-500"
          style={{ background: '#0d1117' }}
        />
        {errorLog && !loading && (
          <div className="rounded-lg border border-red-900 p-3" style={{ background: '#1a0a0a' }}>
            <p className="text-xs font-medium text-red-400 mb-1">Log de erro:</p>
            <pre className="text-xs text-red-300 whitespace-pre-wrap break-all max-h-40 overflow-y-auto">{errorLog}</pre>
          </div>
        )}
        <div className="flex justify-end">
          <button
            type="submit"
            disabled={loading || !state.url.trim()}
            className="flex items-center gap-2 px-6 py-3 bg-navy-600 hover:bg-navy-500 disabled:opacity-50 text-white text-sm font-semibold rounded-lg transition-colors"
          >
            {loading ? (
              <><span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" /> Buscando transcrição...</>
            ) : (
              <>Buscar transcrição <ArrowRight size={15} /></>
            )}
          </button>
        </div>
      </form>
    </div>
  )
}
