import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import Layout from '../../../components/Layout'
import Tabs from '../../../components/ui/Tabs'
import FormField from '../../../components/ui/FormField'
import Select from '../../../components/ui/Select'
import Switch from '../../../components/ui/Switch'
import { api } from '../../../services/api'
import { useToast } from '../../../contexts/ToastContext'

interface Group { id: number; name: string }

export default function UserFormPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const isEdit = id !== 'new'
  const toast = useToast()

  const [groups, setGroups] = useState<Group[]>([])
  const [form, setForm] = useState({ name: '', email: '', password: '', id_group: null as number | null, status: 1 })
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    api.get('/groups').then(r => setGroups(r.data)).catch(() => {})
    if (isEdit) {
      api.get(`/users/${id}`).then(r => {
        const u = r.data
        setForm({ name: u.name, email: u.email, password: '', id_group: u.id_group ?? null, status: u.status })
      }).catch(() => navigate('/administration/users'))
    }
  }, [id])

  function validate() {
    const e: Record<string, string> = {}
    if (!form.name.trim()) e.name = 'Nome é obrigatório'
    if (!form.email.trim()) e.email = 'E-mail é obrigatório'
    if (!isEdit && !form.password.trim()) e.password = 'Senha é obrigatória'
    setErrors(e)
    return Object.keys(e).length === 0
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!validate()) return
    setSaving(true)
    try {
      if (isEdit) await api.put(`/users/${id}`, form)
      else await api.post('/users', form)
      toast.success(isEdit ? 'Usuário atualizado com sucesso!' : 'Usuário cadastrado com sucesso!')
      navigate('/administration/users')
    } catch {
      toast.error('Erro ao salvar. Tente novamente.')
      setErrors({ submit: 'Erro ao salvar. Tente novamente.' })
    } finally {
      setSaving(false)
    }
  }

  const groupOptions = groups.map(g => ({ value: g.id, label: g.name }))

  return (
    <Layout title={isEdit ? 'Editar Usuário' : 'Novo Usuário'} description="Administração / Usuários">
      <form onSubmit={handleSubmit} className="w-full">
        <div className="rounded-xl border border-navy-800 p-6 lg:p-8" style={{ background: '#141920' }}>
          <Tabs tabs={[{
            label: 'Dados Gerais',
            content: (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
                <div className="sm:col-span-2">
                  <FormField label="Nome completo" value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} placeholder="Ex: João Silva" error={errors.name} />
                </div>
                <div className="sm:col-span-2">
                  <FormField label="E-mail" type="email" value={form.email} onChange={e => setForm(f => ({ ...f, email: e.target.value }))} placeholder="joao@exemplo.com" error={errors.email} />
                </div>
                <div className="sm:col-span-2">
                  <FormField label={isEdit ? 'Nova senha (deixe em branco para manter)' : 'Senha'} type="password" value={form.password} onChange={e => setForm(f => ({ ...f, password: e.target.value }))} placeholder="••••••••" error={errors.password} />
                </div>
                <div className="sm:col-span-2">
                  <Select
                    label="Grupo"
                    options={groupOptions}
                    value={form.id_group}
                    onChange={v => setForm(f => ({ ...f, id_group: v as number | null }))}
                    placeholder="Selecione um grupo..."
                  />
                </div>
                <div className="sm:col-span-2 pt-2">
                  <Switch
                    label="Status"
                    description="Usuário ativo pode acessar o sistema"
                    checked={form.status === 1}
                    onChange={v => setForm(f => ({ ...f, status: v ? 1 : 0 }))}
                  />
                </div>
                {errors.submit && <p className="sm:col-span-2 text-red-400 text-sm">{errors.submit}</p>}
              </div>
            )
          }]} />
        </div>

        <div className="flex flex-col-reverse sm:flex-row items-center gap-3 mt-6">
          <button type="button" onClick={() => navigate('/administration/users')} className="w-full sm:w-auto px-6 py-3 text-sm font-medium text-navy-300 hover:text-white border border-navy-700 hover:border-navy-500 rounded-lg transition-colors">
            Cancelar
          </button>
          <button type="submit" disabled={saving} className="w-full sm:w-auto px-8 py-3 bg-navy-600 hover:bg-navy-500 disabled:opacity-50 text-white text-sm font-semibold rounded-lg transition-colors">
            {saving ? 'Salvando...' : isEdit ? 'Salvar alterações' : 'Cadastrar usuário'}
          </button>
        </div>
      </form>
    </Layout>
  )
}
