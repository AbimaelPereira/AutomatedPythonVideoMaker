import { CheckCircle, XCircle, FileJson, Music, ArrowLeft, RotateCcw } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import type { ReelsState } from '../ReelsCutterPage'

interface Props {
  state: ReelsState
  onBack: () => void
}

export default function StepResult({ state, onBack }: Props) {
  const navigate = useNavigate()
  const results = state.results ?? []
  const success = results.filter(r => !r.error)
  const failed  = results.filter(r => r.error)

  return (
    <div>
      <div className="flex items-center gap-3 mb-6">
        <div className="w-10 h-10 rounded-lg bg-emerald-900 flex items-center justify-center">
          <CheckCircle size={18} className="text-emerald-400" />
        </div>
        <div>
          <h2 className="text-base font-semibold text-white">Pipeline concluído</h2>
          <p className="text-xs text-navy-400">{success.length} clips gerados com sucesso{failed.length > 0 ? ` · ${failed.length} com erro` : ''}</p>
        </div>
      </div>

      {/* JSON path */}
      {state.json_path && (
        <div className="flex items-center gap-3 p-3 rounded-lg border border-navy-700 mb-5" style={{ background: '#0d1117' }}>
          <FileJson size={16} className="text-navy-400 shrink-0" />
          <div>
            <p className="text-xs text-navy-500">JSON consolidado salvo em:</p>
            <p className="text-sm font-mono text-white">{state.json_path}</p>
          </div>
        </div>
      )}

      {/* Clips */}
      <div className="space-y-3 mb-6">
        {results.map((r: any, i: number) => (
          <div key={i} className={`rounded-xl border p-4 ${r.error ? 'border-red-900' : 'border-navy-800'}`} style={{ background: '#0d1117' }}>
            <div className="flex items-start gap-3">
              {r.error
                ? <XCircle size={16} className="text-red-400 shrink-0 mt-0.5" />
                : <CheckCircle size={16} className="text-emerald-400 shrink-0 mt-0.5" />
              }
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-white truncate">
                  #{r.clip?.clip_number} — {r.clip?.title}
                </p>
                {r.error ? (
                  <p className="text-xs text-red-400 mt-1">{r.error}</p>
                ) : (
                  <div className="flex items-center gap-4 mt-1">
                    <span className="flex items-center gap-1 text-xs text-navy-500">
                      <Music size={11} /> {r.audio}
                    </span>
                    <span className="text-xs text-navy-500">
                      {r.json?.scenes?.length ?? 0} cenas
                    </span>
                  </div>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>

      <div className="flex items-center justify-between">
        <button onClick={onBack} className="flex items-center gap-2 px-5 py-3 text-sm text-navy-400 hover:text-white border border-navy-700 hover:border-navy-500 rounded-lg transition-colors">
          <ArrowLeft size={15} /> Voltar
        </button>
        <button onClick={() => navigate(0)} className="flex items-center gap-2 px-6 py-3 bg-navy-600 hover:bg-navy-500 text-white text-sm font-semibold rounded-lg transition-colors">
          <RotateCcw size={15} /> Novo pipeline
        </button>
      </div>
    </div>
  )
}
