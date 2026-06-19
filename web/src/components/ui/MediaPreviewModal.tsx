import { X, Trash2, Video } from 'lucide-react'

interface Props {
  open: boolean
  url: string | null
  type: string
  onClose: () => void
  onRemove?: () => void
  removing?: boolean
}

export default function MediaPreviewModal({ open, url, type, onClose, onRemove, removing }: Props) {
  if (!open || !url) return null
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/80" onClick={onClose} />
      <div className="relative max-w-3xl max-h-[85vh] w-full flex items-center justify-center">
        <button
          onClick={onClose}
          className="absolute -top-3 -right-3 p-2 bg-navy-800 hover:bg-navy-700 text-white rounded-full shadow-lg z-10"
          title="Fechar"
        >
          <X size={16} />
        </button>

        {type === 'video' ? (
          <video src={url} controls autoPlay className="max-w-full max-h-[85vh] rounded-xl shadow-2xl" />
        ) : (
          <img src={url} alt="" className="max-w-full max-h-[85vh] rounded-xl shadow-2xl object-contain" />
        )}

        {onRemove && (
          <button
            onClick={onRemove}
            disabled={removing}
            className="absolute bottom-4 left-1/2 -translate-x-1/2 flex items-center gap-2 px-4 py-2 text-sm font-semibold text-white bg-red-700/90 hover:bg-red-600 disabled:opacity-50 rounded-lg shadow-lg backdrop-blur transition-colors"
          >
            <Trash2 size={14} /> {removing ? 'Removendo...' : 'Remover mídia'}
          </button>
        )}
      </div>
    </div>
  )
}

export function MediaThumb({ url, type, onClick }: { url: string; type: string; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="w-12 h-12 rounded-lg overflow-hidden border border-navy-700 bg-navy-900 flex items-center justify-center shrink-0 hover:border-navy-500 transition-colors"
      title="Visualizar"
    >
      {type === 'video' ? (
        <Video size={16} className="text-purple-400" />
      ) : (
        <img src={url} alt="" className="w-full h-full object-cover" loading="lazy" />
      )}
    </button>
  )
}
