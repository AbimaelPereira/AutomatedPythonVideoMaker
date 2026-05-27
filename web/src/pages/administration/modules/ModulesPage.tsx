import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Pencil, Trash2, Plus } from 'lucide-react'
import * as LucideIcons from 'lucide-react'
import Layout from '../../../components/Layout'
import Table from '../../../components/ui/Table'
import Badge from '../../../components/ui/Badge'
import ConfirmModal from '../../../components/ui/ConfirmModal'
import { api } from '../../../services/api'
import { useToast } from '../../../contexts/ToastContext'

interface Module { id: number; name: string; slug: string; icon: string | null; status: number; id_parent: number | null }

function Icon({ name }: { name: string | null }) {
  const I = name ? (LucideIcons as any)[name] : null
  if (!I) return <span className="text-navy-600">—</span>
  return <I size={15} className="text-navy-300" />
}

export default function ModulesPage() {
  const navigate = useNavigate()
  const toast = useToast()
  const [modules, setModules] = useState<Module[]>([])
  const [deleteId, setDeleteId] = useState<number | null>(null)
  const [deleting, setDeleting] = useState(false)

  useEffect(() => {
    api.get('/si-modules').then(r => setModules(r.data)).catch(() => {})
  }, [])

  async function handleDelete() {
    if (deleteId === null) return
    setDeleting(true)
    try {
      await api.delete(`/si-modules/${deleteId}`)
      setModules(m => m.filter(x => x.id !== deleteId))
      toast.success('Módulo excluído com sucesso!')
    } catch {
      toast.error('Erro ao excluir módulo.')
    } finally {
      setDeleting(false)
      setDeleteId(null)
    }
  }

  const parents = modules.filter(m => m.id_parent === null)
  const children = (pid: number) => modules.filter(m => m.id_parent === pid)

  const rows: (Module & { isChild: boolean })[] = []
  parents.forEach(p => {
    rows.push({ ...p, isChild: false })
    children(p.id).forEach(c => rows.push({ ...c, isChild: true }))
  })

  return (
    <Layout title="Módulos" description="Gerenciamento de módulos do sistema">
      <ConfirmModal
        open={deleteId !== null}
        message="O módulo será removido permanentemente."
        onConfirm={handleDelete}
        onCancel={() => setDeleteId(null)}
        loading={deleting}
      />

      <div className="flex justify-end mb-6">
        <button
          onClick={() => navigate('/administration/modules/new')}
          className="flex items-center gap-2 bg-navy-600 hover:bg-navy-500 text-white text-sm font-semibold px-5 py-2.5 rounded-lg transition-colors"
        >
          <Plus size={16} /> Novo Módulo
        </button>
      </div>

      <Table
        keyField="id"
        rows={rows}
        columns={[
          { label: '#', width: '60px', render: r => <span className="text-navy-500 text-xs">{r.id}</span> },
          { label: 'Ícone', width: '60px', render: r => <Icon name={r.icon} /> },
          {
            label: 'Nome', render: r => (
              <span className={`font-medium ${r.isChild ? 'text-navy-300 pl-4' : 'text-white'}`}>
                {r.isChild ? '↳ ' : ''}{r.name}
              </span>
            )
          },
          { label: 'Slug', render: r => <span className="text-navy-500 font-mono text-xs">{r.slug}</span> },
          { label: 'Status', width: '90px', render: r => <Badge active={r.status === 1} /> },
          {
            label: 'Ações', width: '120px', render: r => (
              <div className="flex items-center gap-2">
                <button
                  onClick={() => navigate(`/administration/modules/${r.id}`)}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-navy-300 hover:text-white bg-navy-800 hover:bg-navy-700 rounded-lg transition-colors"
                >
                  <Pencil size={12} /> Editar
                </button>
                <button
                  onClick={() => setDeleteId(r.id)}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-red-400 hover:text-white bg-red-950 hover:bg-red-800 rounded-lg transition-colors"
                >
                  <Trash2 size={12} /> Excluir
                </button>
              </div>
            )
          },
        ]}
      />
    </Layout>
  )
}
