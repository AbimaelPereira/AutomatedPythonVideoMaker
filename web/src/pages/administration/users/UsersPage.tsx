import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Pencil, Trash2, Plus } from 'lucide-react'
import Layout from '../../../components/Layout'
import Table from '../../../components/ui/Table'
import Badge from '../../../components/ui/Badge'
import ConfirmModal from '../../../components/ui/ConfirmModal'
import { api } from '../../../services/api'
import { useToast } from '../../../contexts/ToastContext'

interface User {
  id: number
  name: string
  email: string
  status: number
  group: { id: number; name: string } | null
}

export default function UsersPage() {
  const navigate = useNavigate()
  const toast = useToast()
  const [users, setUsers] = useState<User[]>([])
  const [deleteId, setDeleteId] = useState<number | null>(null)
  const [deleting, setDeleting] = useState(false)

  useEffect(() => {
    api.get('/users').then(r => setUsers(r.data)).catch(() => {})
  }, [])

  async function handleDelete() {
    if (deleteId === null) return
    setDeleting(true)
    try {
      await api.delete(`/users/${deleteId}`)
      setUsers(u => u.filter(x => x.id !== deleteId))
      toast.success('Usuário excluído com sucesso!')
    } catch {
      toast.error('Erro ao excluir usuário.')
    } finally {
      setDeleting(false)
      setDeleteId(null)
    }
  }

  return (
    <Layout title="Usuários" description="Gerenciamento de usuários do sistema">
      <ConfirmModal
        open={deleteId !== null}
        message="O usuário será removido permanentemente."
        onConfirm={handleDelete}
        onCancel={() => setDeleteId(null)}
        loading={deleting}
      />

      <div className="flex justify-end mb-6">
        <button
          onClick={() => navigate('/administration/users/new')}
          className="flex items-center gap-2 bg-navy-600 hover:bg-navy-500 text-white text-sm font-semibold px-5 py-2.5 rounded-lg transition-colors"
        >
          <Plus size={16} /> Novo Usuário
        </button>
      </div>

      <Table
        keyField="id"
        rows={users}
        columns={[
          { label: '#', width: '60px', render: r => <span className="text-navy-500 text-xs">{r.id}</span> },
          { label: 'Nome', render: r => <span className="text-white font-medium">{r.name}</span> },
          { label: 'E-mail', render: r => <span className="text-navy-300">{r.email}</span> },
          { label: 'Grupo', render: r => r.group?.name ?? <span className="text-navy-600">—</span> },
          { label: 'Status', width: '90px', render: r => <Badge active={r.status === 1} /> },
          {
            label: 'Ações', width: '120px', render: r => (
              <div className="flex items-center gap-2">
                <button
                  onClick={() => navigate(`/administration/users/${r.id}`)}
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
