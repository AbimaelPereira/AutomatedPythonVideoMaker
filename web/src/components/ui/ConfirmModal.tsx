import { Trash2 } from 'lucide-react'

interface Props {
  open: boolean
  title?: string
  message?: string
  onConfirm: () => void
  onCancel: () => void
  loading?: boolean
}

export default function ConfirmModal({ open, title = 'Confirmar exclusão', message = 'Esta ação não pode ser desfeita.', onConfirm, onCancel, loading }: Props) {
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/70" onClick={onCancel} />
      <div className="relative w-full max-w-sm rounded-xl border border-red-900 p-6 shadow-2xl" style={{ background: '#141920' }}>
        <div className="flex items-center justify-center w-12 h-12 rounded-full bg-red-950 border border-red-800 mx-auto mb-4">
          <Trash2 size={20} className="text-red-400" />
        </div>
        <h3 className="text-base font-semibold text-white text-center mb-1">{title}</h3>
        <p className="text-sm text-navy-400 text-center mb-6">{message}</p>
        <div className="flex gap-3">
          <button
            onClick={onCancel}
            disabled={loading}
            className="flex-1 px-4 py-2.5 text-sm font-medium text-navy-300 hover:text-white border border-navy-700 hover:border-navy-500 rounded-lg transition-colors"
          >
            Cancelar
          </button>
          <button
            onClick={onConfirm}
            disabled={loading}
            className="flex-1 px-4 py-2.5 text-sm font-semibold text-white bg-red-700 hover:bg-red-600 disabled:opacity-50 rounded-lg transition-colors"
          >
            {loading ? 'Excluindo...' : 'Excluir'}
          </button>
        </div>
      </div>
    </div>
  )
}
