import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { FolderOpen, Pencil, Trash2, Plus, Image, Video, FileQuestion } from 'lucide-react'
import Layout from '../../components/Layout'
import ConfirmModal from '../../components/ui/ConfirmModal'
import { api } from '../../services/api'
import { useToast } from '../../contexts/ToastContext'

interface Asset {
  id: number
  name: string
  slug: string
  description: string | null
  created_at: string
  midia_count: number
}

export default function RemoteAssetsPage() {
  const navigate = useNavigate()
  const toast = useToast()
  const [assets, setAssets] = useState<Asset[]>([])
  const [deleteId, setDeleteId] = useState<number | null>(null)
  const [deleting, setDeleting] = useState(false)
  const [search, setSearch] = useState('')

  useEffect(() => {
    api.get('/remote-assets').then(r => setAssets(r.data)).catch(() => {})
  }, [])

  async function handleDelete() {
    if (deleteId === null) return
    setDeleting(true)
    try {
      await api.delete(`/remote-assets/${deleteId}`)
      setAssets(a => a.filter(x => x.id !== deleteId))
      toast.success('Asset excluído com sucesso!')
    } catch {
      toast.error('Erro ao excluir asset.')
    } finally {
      setDeleting(false)
      setDeleteId(null)
    }
  }

  const filtered = assets.filter(a =>
    a.name.toLowerCase().includes(search.toLowerCase()) ||
    a.slug.toLowerCase().includes(search.toLowerCase())
  )

  return (
    <Layout title="Remote Assets" description="Gerenciamento de assets remotos">
      <ConfirmModal
        open={deleteId !== null}
        message="O asset e todas as suas mídias serão removidos permanentemente."
        onConfirm={handleDelete}
        onCancel={() => setDeleteId(null)}
        loading={deleting}
      />

      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 mb-6">
        <input
          type="text"
          placeholder="Buscar por nome ou slug..."
          value={search}
          onChange={e => setSearch(e.target.value)}
          className="w-full sm:w-72 border border-navy-700 rounded-lg px-4 py-2 text-sm text-white placeholder-navy-500 focus:outline-none focus:border-navy-500"
          style={{ background: '#0d1117' }}
        />
        <button
          onClick={() => navigate('/remote-assets/assets/new')}
          className="shrink-0 flex items-center gap-2 bg-navy-600 hover:bg-navy-500 text-white text-sm font-semibold px-5 py-2.5 rounded-lg transition-colors"
        >
          <Plus size={16} /> Novo Asset
        </button>
      </div>

      {filtered.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 text-navy-600">
          <FolderOpen size={48} className="mb-3 opacity-30" />
          <p className="text-sm">Nenhum asset encontrado.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {filtered.map(asset => (
            <div
              key={asset.id}
              className="rounded-xl border border-navy-800 p-5 flex flex-col gap-3 hover:border-navy-600 transition-colors cursor-pointer group"
              style={{ background: '#141920' }}
              onClick={() => navigate(`/remote-assets/assets/${asset.id}`)}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="w-10 h-10 rounded-lg bg-navy-800 flex items-center justify-center shrink-0">
                  <FolderOpen size={18} className="text-navy-400" />
                </div>
                <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                  <button
                    onClick={e => { e.stopPropagation(); navigate(`/remote-assets/assets/${asset.id}/edit`) }}
                    className="p-1.5 text-navy-400 hover:text-white bg-navy-800 hover:bg-navy-700 rounded-lg transition-colors"
                  >
                    <Pencil size={13} />
                  </button>
                  <button
                    onClick={e => { e.stopPropagation(); setDeleteId(asset.id) }}
                    className="p-1.5 text-red-400 hover:text-white bg-red-950 hover:bg-red-800 rounded-lg transition-colors"
                  >
                    <Trash2 size={13} />
                  </button>
                </div>
              </div>

              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold text-white truncate">{asset.name}</p>
                <p className="text-xs text-navy-500 font-mono truncate mt-0.5">{asset.slug}</p>
                {asset.description && (
                  <p className="text-xs text-navy-400 mt-1.5 line-clamp-2">{asset.description}</p>
                )}
              </div>

              <div className="flex items-center gap-1.5 pt-2 border-t border-navy-800">
                <div className="flex items-center gap-1 text-xs text-navy-500">
                  <Image size={11} />
                  <Video size={11} />
                  <FileQuestion size={11} />
                </div>
                <span className="text-xs text-navy-400 ml-1">
                  {asset.midia_count} {asset.midia_count === 1 ? 'mídia' : 'mídias'}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </Layout>
  )
}
