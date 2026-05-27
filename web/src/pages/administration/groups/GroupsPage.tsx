import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Pencil, Trash2, Plus } from 'lucide-react'
import Layout from '../../../components/Layout'
import Table from '../../../components/ui/Table'
import Badge from '../../../components/ui/Badge'
import ConfirmModal from '../../../components/ui/ConfirmModal'
import { api } from '../../../services/api'
import { useToast } from '../../../contexts/ToastContext'

interface Group { id: number; name: string; status: number }

export default function GroupsPage() {
  const navigate = useNavigate()
  const toast = useToast()
  const [groups, setGroups] = useState<Group[]>([])
  const [deleteId, setDeleteId] = useState<number | null>(null)
  const [deleting, setDeleting] = useState(false)

  useEffect(() => {
    api.get('/groups').then(r => setGroups(r.data)).catch(() => {})
  }, [])

  async function handleDelete() {
    if (deleteId === null) return
    setDeleting(true)
    try {
      await api.delete(`/groups/${deleteId}`)
      setGroups(g => g.filter(x => x.id !== deleteId))
      toast.success('Grupo excluído com sucesso!')
    } catch {
      toast.error('Erro ao excluir grupo.')
    } finally {
      setDeleting(false)
      setDeleteId(null)
    }
  }

  return (
    <Layout title="Grupos" description="Gerenciamento de grupos e permissões">
      <ConfirmModal
        open={deleteId !== null}
        message="O grupo será removido permanentemente."
        onConfirm={handleDelete}
        onCancel={() => setDeleteId(null)}
        loading={deleting}
      />

      <div className="flex justify-end mb-6">
        <button
          onClick={() => navigate('/administration/groups/new')}
          className="flex items-center gap-2 bg-navy-600 hover:bg-navy-500 text-white text-sm font-semibold px-5 py-2.5 rounded-lg transition-colors"
        >
          <Plus size={16} /> Novo Grupo
        </button>
      </div>

      <Table
        keyField="id"
        rows={groups}
        columns={[
          { label: '#', width: '60px', render: r => <span className="text-navy-500 text-xs">{r.id}</span> },
          { label: 'Nome', render: r => <span className="text-white font-medium">{r.name}</span> },
          { label: 'Status', width: '90px', render: r => <Badge active={r.status === 1} /> },
          {
            label: 'Ações', width: '120px', render: r => (
              <div className="flex items-center gap-2">
                <button
                  onClick={() => navigate(`/administration/groups/${r.id}`)}
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
