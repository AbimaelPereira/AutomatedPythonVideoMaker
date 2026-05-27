import { useState } from 'react'
import { ArrowLeft, ArrowRight, FileJson, Save } from 'lucide-react'
import { api } from '../../../services/api'
import { useToast } from '../../../contexts/ToastContext'
import type { ReelsState } from '../ReelsCutterPage'
import ClipJsonEditor, { type ClipJson } from '../components/ClipJsonEditor'

interface Props {
  state: ReelsState
  update: (patch: Partial<ReelsState>) => void
  onNext: () => void
  onBack: () => void
}

export default function StepEdit({ state, update, onNext, onBack }: Props) {
  const toast = useToast()
  const [saving, setSaving] = useState(false)

  // Extrai os JSONs dos resultados gerados
  const [clipJsons, setClipJsons] = useState<ClipJson[]>(() =>
    (state.results ?? [])
      .filter(r => !r.error && r.json)
      .map(r => r.json as ClipJson)
  )

  function handleChange(i: number, updated: ClipJson) {
    setClipJsons(prev => prev.map((c, ci) => ci === i ? updated : c))
  }

  async function handleSave() {
    setSaving(true)
    try {
      await api.post('/reelscutter/save-jsons', {
        json_path: state.json_path,
        clips: clipJsons,
      })
      toast.success('JSONs salvos com sucesso.')
      // Atualiza os resultados no state para refletir as edições
      update({
        results: (state.results ?? []).map(r => {
          const edited = clipJsons.find(c => c.slug === r.json?.slug)
          return edited ? { ...r, json: edited } : r
        })
      })
    } catch {
      toast.error('Erro ao salvar os JSONs.')
    } finally {
      setSaving(false)
    }
  }

  if (clipJsons.length === 0) {
    return (
      <div>
        <div className="text-center py-12 text-navy-600 text-sm">
          Nenhum clip gerado com sucesso para editar.
        </div>
        <div className="flex justify-between mt-6">
          <button onClick={onBack} className="flex items-center gap-2 px-5 py-3 text-sm text-navy-400 hover:text-white border border-navy-700 hover:border-navy-500 rounded-lg transition-colors">
            <ArrowLeft size={15} /> Voltar
          </button>
          <button onClick={onNext} className="flex items-center gap-2 px-6 py-3 bg-navy-600 hover:bg-navy-500 text-white text-sm font-semibold rounded-lg transition-colors">
            Continuar <ArrowRight size={15} />
          </button>
        </div>
      </div>
    )
  }

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-navy-800 flex items-center justify-center">
            <FileJson size={18} className="text-navy-300" />
          </div>
          <div>
            <h2 className="text-base font-semibold text-white">Edição dos clips</h2>
            <p className="text-xs text-navy-400">
              {clipJsons.length} clip{clipJsons.length !== 1 ? 's' : ''} · clique em um card para expandir e editar
            </p>
          </div>
        </div>
        <button
          onClick={handleSave}
          disabled={saving}
          className="flex items-center gap-1.5 text-xs px-3 py-2 rounded-lg transition-colors text-white disabled:opacity-50"
          style={{ background: '#1a2540', border: '1px solid #2f4a8f' }}
        >
          <Save size={13} /> {saving ? 'Salvando...' : 'Salvar JSONs'}
        </button>
      </div>

      {/* Lista */}
      <div className="space-y-2 mb-6 max-h-[60vh] overflow-y-auto rc-scroll pr-1">
        {clipJsons.map((clip, i) => (
          <ClipJsonEditor
            key={clip.slug}
            index={i}
            clip={clip}
            onChange={updated => handleChange(i, updated)}
          />
        ))}
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between">
        <button
          onClick={onBack}
          className="flex items-center gap-2 px-5 py-3 text-sm text-navy-400 hover:text-white border border-navy-700 hover:border-navy-500 rounded-lg transition-colors"
        >
          <ArrowLeft size={15} /> Voltar
        </button>
        <button
          onClick={onNext}
          className="flex items-center gap-2 px-6 py-3 bg-navy-600 hover:bg-navy-500 text-white text-sm font-semibold rounded-lg transition-colors"
        >
          Concluir <ArrowRight size={15} />
        </button>
      </div>
    </div>
  )
}
