import { useState, useEffect } from 'react'
import { ArrowLeft, ArrowRight, Scissors, Loader2, Clock, Tag, Trash2, Play, Pause, Plus } from 'lucide-react'
import { api, audioUrl } from '../../../services/api'
import { useToast } from '../../../contexts/ToastContext'
import type { ReelsState } from '../ReelsCutterPage'
import { useAudioPlayer } from '../hooks/useAudioPlayer'
import ClipEditModal, { type ClipData } from '../components/ClipEditModal'
import ClipFormModal from '../components/ClipFormModal'

interface Props {
  state: ReelsState
  update: (patch: Partial<ReelsState>) => void
  onNext: () => void
  onBack: () => void
}

const CATEGORY_COLORS: Record<string, string> = {
  revelacao:  'bg-purple-900 text-purple-300',
  confronto:  'bg-orange-900 text-orange-300',
  promessa:   'bg-blue-900 text-blue-300',
  historia:   'bg-teal-900 text-teal-300',
  declaracao: 'bg-yellow-900 text-yellow-300',
  chamado:    'bg-pink-900 text-pink-300',
}

function fmt(s: number) {
  const m  = Math.floor(s / 60)
  const ss = Math.floor(s % 60)
  return `${String(m).padStart(2, '0')}:${String(ss).padStart(2, '0')}`
}

export default function StepReview({ state, update, onNext, onBack }: Props) {
  const toast  = useToast()
  const [loading,  setLoading]  = useState(false)
  const [editClip, setEditClip] = useState<ClipData | null>(null)
  const [showForm, setShowForm] = useState(false)

  const [audioPath, setAudioPath] = useState('')
  useEffect(() => {
    if (state.audio_path) audioUrl(state.audio_path).then(setAudioPath)
  }, [state.audio_path])
  const { state: ps, play, pause } = useAudioPlayer(audioPath)
  const [previewClipNum, setPreviewClipNum] = useState<number | null>(null)

  const [originalClips] = useState<ClipData[]>(() => state.clips as ClipData[])
  const clips: ClipData[] = state.clips as ClipData[]

  function deleteClip(clipNumber: number) {
    update({ clips: state.clips.filter((c: any) => c.clip_number !== clipNumber) })
    if (previewClipNum === clipNumber) { pause(); setPreviewClipNum(null) }
  }

  function saveClip(updated: ClipData) {
    update({ clips: state.clips.map((c: any) => c.clip_number === updated.clip_number ? { ...c, ...updated } : c) })
  }

  function addClip(newClip: ClipData) {
    update({ clips: [...state.clips, newClip] })
  }

  function handleCardPlay(e: React.MouseEvent, clip: ClipData) {
    e.stopPropagation()
    if (previewClipNum === clip.clip_number && ps.playing) {
      pause(); setPreviewClipNum(null)
    } else {
      setPreviewClipNum(clip.clip_number)
      play({ start: clip.start_time, end: clip.end_time })
    }
  }

  const nextClipNumber = clips.length > 0 ? Math.max(...clips.map(c => c.clip_number)) + 1 : 1

  async function handleGenerate() {
    if (clips.length === 0) { toast.warning('Adicione ao menos um clip.'); return }
    setLoading(true)
    try {
      const r = await api.post('/reelscutter/generate', {
        audio_path: state.audio_path,
        clips,
        config: state.config,
      })
      update({ results: r.data.results, json_path: r.data.json_path, selected_clips: clips })
      onNext()
    } catch {
      toast.error('Erro ao gerar os clips.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-navy-800 flex items-center justify-center">
            <Scissors size={18} className="text-navy-300" />
          </div>
          <div>
            <h2 className="text-base font-semibold text-white">Curadoria dos clips</h2>
            <p className="text-xs text-navy-400">{clips.length} cortes</p>
          </div>
        </div>
        <button
          onClick={() => setShowForm(true)}
          className="flex items-center gap-1.5 text-xs px-3 py-2 bg-navy-700 hover:bg-navy-600 text-white rounded-lg transition-colors"
        >
          <Plus size={13} /> Novo corte
        </button>
      </div>

      {/* Cards */}
      <div className="space-y-2 mb-6 max-h-[60vh] overflow-y-auto rc-scroll pr-1">
        {clips.length === 0 && (
          <div className="text-center py-12 text-navy-600 text-sm">
            Nenhum corte. Crie um manualmente com "Novo corte".
          </div>
        )}

        {clips.map(clip => {
          const isPlaying = previewClipNum === clip.clip_number && ps.playing
          const duration  = (clip.end_time - clip.start_time).toFixed(0)
          const isGemini  = originalClips.some(o => o.clip_number === clip.clip_number)
          const catKey    = clip.category?.split('|')[0] ?? ''

          return (
            <div
              key={clip.clip_number}
              onClick={() => setEditClip(clip)}
              className="rounded-xl border border-navy-800 p-4 cursor-pointer transition-all hover:border-navy-600"
              style={{ background: '#0d1117' }}
            >
              <div className="flex items-start gap-3">
                {/* Conteúdo */}
                <div className="flex-1 min-w-0">
                  <div className="flex flex-wrap items-center gap-2 mb-1">
                    <span className="text-sm font-semibold text-white">
                      #{clip.clip_number} — {clip.title}
                    </span>
                    {clip.category && (
                      <span className={`text-xs px-2 py-0.5 rounded-full ${CATEGORY_COLORS[catKey] ?? 'bg-navy-800 text-navy-400'}`}>
                        {catKey}
                      </span>
                    )}
                    {!isGemini && (
                      <span className="text-xs px-2 py-0.5 rounded-full bg-navy-800 text-navy-500">manual</span>
                    )}
                  </div>

                  <div className="flex items-center gap-4 text-xs text-navy-600">
                    <span className="flex items-center gap-1">
                      <Clock size={11} />
                      {duration}s · {fmt(clip.start_time)} → {fmt(clip.end_time)}
                    </span>
                    {clip.scenes_text && (
                      <span className="flex items-center gap-1">
                        <Tag size={11} /> {clip.scenes_text.length} cenas
                      </span>
                    )}
                  </div>

                  {clip.hook && (
                    <p className="text-xs text-navy-400 italic mt-1 truncate">"{clip.hook}"</p>
                  )}
                </div>

                {/* Ações */}
                <div className="flex items-center gap-1 shrink-0" onClick={e => e.stopPropagation()}>
                  <button
                    onClick={e => handleCardPlay(e, clip)}
                    title={isPlaying ? 'Pausar' : 'Ouvir trecho'}
                    className={`p-2 rounded-lg transition-colors ${isPlaying ? 'bg-navy-600 text-white' : 'text-navy-500 hover:text-white hover:bg-navy-800'}`}
                  >
                    {isPlaying ? <Pause size={14} /> : <Play size={14} />}
                  </button>
                  <button
                    onClick={() => deleteClip(clip.clip_number)}
                    title="Excluir corte"
                    className="p-2 rounded-lg text-navy-700 hover:text-red-400 hover:bg-navy-800 transition-colors"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
            </div>
          )
        })}
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between">
        <button
          onClick={onBack}
          disabled={loading}
          className="flex items-center gap-2 px-5 py-3 text-sm text-navy-400 hover:text-white border border-navy-700 hover:border-navy-500 rounded-lg transition-colors disabled:opacity-50"
        >
          <ArrowLeft size={15} /> Voltar
        </button>
        <button
          onClick={handleGenerate}
          disabled={loading || clips.length === 0}
          className="flex items-center gap-2 px-6 py-3 bg-navy-600 hover:bg-navy-500 disabled:opacity-40 text-white text-sm font-semibold rounded-lg transition-colors"
        >
          {loading
            ? <><Loader2 size={15} className="animate-spin" /> Gerando...</>
            : <><Scissors size={15} /> Gerar {clips.length} clip{clips.length !== 1 ? 's' : ''} <ArrowRight size={15} /></>
          }
        </button>
      </div>

      {editClip && (
        <ClipEditModal
          clip={editClip}
          originalClip={originalClips.find(o => o.clip_number === editClip.clip_number)}
          transcript={state.transcript}
          audioPath={audioPath}
          onSave={saveClip}
          onClose={() => setEditClip(null)}
        />
      )}

      {showForm && (
        <ClipFormModal
          transcript={state.transcript}
          nextClipNumber={nextClipNumber}
          onSave={addClip}
          onClose={() => setShowForm(false)}
        />
      )}
    </div>
  )
}
