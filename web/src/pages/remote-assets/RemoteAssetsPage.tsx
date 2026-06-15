import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { FolderOpen, Pencil, Trash2, Plus, CheckCircle, AlertTriangle, Images, ImagePlus } from 'lucide-react'
import Layout from '../../components/Layout'
import ConfirmModal from '../../components/ui/ConfirmModal'
import AddMidiaModal from '../../components/ui/AddMidiaModal'
import { googleImagesUrl } from '../../components/ui/CopyButton'
import { api } from '../../services/api'
import { useToast } from '../../contexts/ToastContext'

interface Asset {
  id: number
  name: string
  slug: string
  description: string | null
  created_at: string
  midia_count: number
  valid_count: number
  invalid_count: number
  last_used: string | null
}

type Filtro = 'all' | 'empty' | 'no_valid'

function formatDate(d: string | null) {
  if (!d) return '—'
  const dt = new Date(d)
  if (isNaN(dt.getTime())) return '—'
  return dt.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit', year: '2-digit' })
}

export default function RemoteAssetsPage() {
  const navigate = useNavigate()
  const toast = useToast()
  const [assets, setAssets] = useState<Asset[]>([])
  const [deleteId, setDeleteId] = useState<number | null>(null)
  const [deleting, setDeleting] = useState(false)
  const [search, setSearch] = useState('')
  const [filtro, setFiltro] = useState<Filtro>('all')
  const [addMidiaAsset, setAddMidiaAsset] = useState<Asset | null>(null)

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

  const totals = useMemo(() => assets.reduce(
    (acc, a) => {
      acc.slugs += 1
      acc.valid += a.valid_count ?? 0
      acc.invalid += a.invalid_count ?? 0
      const lu = a.last_used ? new Date(a.last_used).getTime() : 0
      if (lu > acc.lastUsedTs) { acc.lastUsedTs = lu; acc.lastUsed = a.last_used }
      return acc
    },
    { slugs: 0, valid: 0, invalid: 0, lastUsed: null as string | null, lastUsedTs: 0 }
  ), [assets])

  const filtered = useMemo(() => {
    const q = search.toLowerCase()
    return assets.filter(a => {
      const matchSearch = a.name.toLowerCase().includes(q) || a.slug.toLowerCase().includes(q)
      if (!matchSearch) return false
      if (filtro === 'empty') return (a.midia_count ?? 0) === 0
      if (filtro === 'no_valid') return (a.valid_count ?? 0) === 0
      return true
    })
  }, [assets, search, filtro])

  const filtros: { key: Filtro; label: string }[] = [
    { key: 'all', label: 'Todos' },
    { key: 'no_valid', label: 'Sem válidas' },
    { key: 'empty', label: 'Vazios' },
  ]

  return (
    <Layout title="Remote Assets" description="Gerenciamento de assets remotos">
      <ConfirmModal
        open={deleteId !== null}
        message="O asset e todas as suas mídias serão removidos permanentemente."
        onConfirm={handleDelete}
        onCancel={() => setDeleteId(null)}
        loading={deleting}
      />

      {addMidiaAsset && (
        <AddMidiaModal
          open
          assetId={addMidiaAsset.id}
          assetName={addMidiaAsset.name}
          assetSlug={addMidiaAsset.slug}
          onClose={() => setAddMidiaAsset(null)}
          onAdded={count => setAssets(list => list.map(a =>
            a.id === addMidiaAsset.id
              ? { ...a, midia_count: (a.midia_count ?? 0) + count, valid_count: (a.valid_count ?? 0) + count }
              : a
          ))}
        />
      )}

      {/* Cards de resumo */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
        <SummaryCard label="Slugs" value={totals.slugs} icon={<FolderOpen size={16} className="text-navy-400" />} />
        <SummaryCard label="Válidas" value={totals.valid} icon={<CheckCircle size={16} className="text-emerald-400" />} />
        <SummaryCard label="Inválidas" value={totals.invalid} icon={<AlertTriangle size={16} className="text-red-400" />} />
        <SummaryCard label="Último uso" value={formatDate(totals.lastUsed)} icon={<span className="text-navy-400 text-xs">🕑</span>} small />
      </div>

      {/* Busca + filtros + novo */}
      <div className="flex flex-col gap-3 mb-5">
        <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
          <input
            type="text"
            placeholder="Buscar por nome ou slug..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="w-full sm:w-72 border border-navy-700 rounded-lg px-4 py-2.5 text-sm text-white placeholder-navy-500 focus:outline-none focus:border-navy-500"
            style={{ background: '#0d1117' }}
          />
          <button
            onClick={() => navigate('/remote-assets/assets/new')}
            className="shrink-0 flex items-center justify-center gap-2 bg-navy-600 hover:bg-navy-500 text-white text-sm font-semibold px-5 py-2.5 rounded-lg transition-colors"
          >
            <Plus size={16} /> Novo Asset
          </button>
        </div>
        <div className="flex gap-2 overflow-x-auto -mx-1 px-1">
          {filtros.map(f => (
            <button
              key={f.key}
              onClick={() => setFiltro(f.key)}
              className={`shrink-0 px-3 py-1.5 text-xs font-medium rounded-lg transition-colors ${
                filtro === f.key ? 'bg-navy-600 text-white' : 'text-navy-400 bg-navy-800 hover:text-white'
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {filtered.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 text-navy-600">
          <FolderOpen size={48} className="mb-3 opacity-30" />
          <p className="text-sm">Nenhum asset encontrado.</p>
        </div>
      ) : (
        <div className="rounded-xl border border-navy-800 overflow-x-auto">
          <table className="w-full text-sm min-w-[640px]">
            <thead>
              <tr className="border-b border-navy-800 text-left" style={{ background: '#141920' }}>
                <th className="px-4 py-3 text-xs font-semibold text-navy-400 uppercase tracking-wider">Asset</th>
                <th className="px-4 py-3 text-xs font-semibold text-navy-400 uppercase tracking-wider w-20 text-center">Total</th>
                <th className="px-4 py-3 text-xs font-semibold text-navy-400 uppercase tracking-wider w-24 text-center">Válidas</th>
                <th className="px-4 py-3 text-xs font-semibold text-navy-400 uppercase tracking-wider w-24 text-center">Inválidas</th>
                <th className="px-4 py-3 text-xs font-semibold text-navy-400 uppercase tracking-wider w-28 hidden md:table-cell">Último uso</th>
                <th className="px-4 py-3 text-xs font-semibold text-navy-400 uppercase tracking-wider w-32 text-right">Ações</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map(asset => (
                <tr
                  key={asset.id}
                  className="border-b border-navy-900 hover:bg-navy-900 transition-colors cursor-pointer"
                  onClick={() => navigate(`/remote-assets/assets/${asset.id}`)}
                >
                  <td className="px-4 py-3">
                    <p className="text-sm font-semibold text-white truncate">{asset.name}</p>
                    <p className="text-xs text-navy-500 font-mono truncate">{asset.slug}</p>
                  </td>
                  <td className="px-4 py-3 text-center text-navy-300">{asset.midia_count ?? 0}</td>
                  <td className="px-4 py-3 text-center">
                    <span className={(asset.valid_count ?? 0) === 0 ? 'text-navy-600' : 'text-emerald-400'}>{asset.valid_count ?? 0}</span>
                  </td>
                  <td className="px-4 py-3 text-center">
                    <span className={(asset.invalid_count ?? 0) === 0 ? 'text-navy-600' : 'text-red-400'}>{asset.invalid_count ?? 0}</span>
                  </td>
                  <td className="px-4 py-3 text-xs text-navy-400 hidden md:table-cell">{formatDate(asset.last_used)}</td>
                  <td className="px-4 py-3">
                    <div className="flex items-center justify-end gap-1.5" onClick={e => e.stopPropagation()}>
                      <button
                        onClick={() => setAddMidiaAsset(asset)}
                        title="Adicionar mídias"
                        className="p-2 text-emerald-400 hover:text-white bg-emerald-950 hover:bg-emerald-800 rounded-lg transition-colors"
                      >
                        <ImagePlus size={14} />
                      </button>
                      <a
                        href={googleImagesUrl(asset.name || asset.slug)}
                        target="_blank"
                        rel="noreferrer"
                        title="Buscar no Google Imagens"
                        className="p-2 text-navy-400 hover:text-white bg-navy-800 hover:bg-navy-700 rounded-lg transition-colors"
                      >
                        <Images size={14} />
                      </a>
                      <button
                        onClick={() => navigate(`/remote-assets/assets/${asset.id}/edit`)}
                        title="Editar"
                        className="p-2 text-navy-400 hover:text-white bg-navy-800 hover:bg-navy-700 rounded-lg transition-colors"
                      >
                        <Pencil size={13} />
                      </button>
                      <button
                        onClick={() => setDeleteId(asset.id)}
                        title="Excluir"
                        className="p-2 text-red-400 hover:text-white bg-red-950 hover:bg-red-800 rounded-lg transition-colors"
                      >
                        <Trash2 size={13} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Layout>
  )
}

function SummaryCard({ label, value, icon, small }: { label: string; value: number | string; icon: React.ReactNode; small?: boolean }) {
  return (
    <div className="rounded-xl border border-navy-800 p-4 flex items-center gap-3" style={{ background: '#141920' }}>
      <div className="w-9 h-9 rounded-lg bg-navy-800 flex items-center justify-center shrink-0">{icon}</div>
      <div className="min-w-0">
        <p className="text-xs text-navy-500">{label}</p>
        <p className={`font-semibold text-white truncate ${small ? 'text-sm' : 'text-lg'}`}>{value}</p>
      </div>
    </div>
  )
}
