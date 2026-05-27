import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import Layout from '../../../components/Layout'
import Tabs from '../../../components/ui/Tabs'
import FormField from '../../../components/ui/FormField'
import Select from '../../../components/ui/Select'
import Switch from '../../../components/ui/Switch'
import { api } from '../../../services/api'
import { useToast } from '../../../contexts/ToastContext'

interface Parent { id: number; name: string }

export default function ModuleFormPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const isEdit = id !== 'new'
  const toast = useToast()

  const [parents, setParents] = useState<Parent[]>([])
  const [form, setForm] = useState({
    name: '', slug: '', icon: '',
    id_parent: null as number | null,
    order_by: '1', actions: 'view',
    show_in_menu: 1, status: 1,
  })
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    api.get('/si-modules/parents').then(r => setParents(r.data)).catch(() => {})
    if (isEdit) {
      api.get(`/si-modules/${id}`).then(r => {
        const m = r.data
        setForm({
          name: m.name, slug: m.slug ?? '', icon: m.icon ?? '',
          id_parent: m.id_parent ?? null, order_by: String(m.order_by),
          actions: m.actions ?? '', show_in_menu: m.show_in_menu, status: m.status,
        })
      }).catch(() => navigate('/administration/modules'))
    }
  }, [id])

  function validate() {
    const e: Record<string, string> = {}
    if (!form.name.trim()) e.name = 'Nome é obrigatório'
    if (!form.slug.trim()) e.slug = 'Slug é obrigatório'
    setErrors(e)
    return Object.keys(e).length === 0
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!validate()) return
    setSaving(true)
    try {
      const payload = { ...form, order_by: Number(form.order_by) }
      if (isEdit) await api.put(`/si-modules/${id}`, payload)
      else await api.post('/si-modules', payload)
      toast.success(isEdit ? 'Módulo atualizado com sucesso!' : 'Módulo cadastrado com sucesso!')
      navigate('/administration/modules')
    } catch {
      toast.error('Erro ao salvar. Tente novamente.')
      setErrors({ submit: 'Erro ao salvar.' })
    } finally {
      setSaving(false)
    }
  }

  const parentOptions = parents
    .filter(p => String(p.id) !== id)
    .map(p => ({ value: p.id, label: p.name }))

  return (
    <Layout title={isEdit ? 'Editar Módulo' : 'Novo Módulo'} description="Administração / Módulos">
      <form onSubmit={handleSubmit} className="w-full">
        <div className="rounded-xl border border-navy-800 p-6 lg:p-8" style={{ background: '#141920' }}>
          <Tabs tabs={[{
            label: 'Dados Gerais',
            content: (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
                <div className="sm:col-span-2">
                  <FormField label="Nome" value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} placeholder="Ex: Administração" error={errors.name} />
                </div>
                <FormField label="Slug" value={form.slug} onChange={e => setForm(f => ({ ...f, slug: e.target.value }))} placeholder="Ex: administration/users" error={errors.slug} />
                <FormField label="Ícone (Lucide)" value={form.icon} onChange={e => setForm(f => ({ ...f, icon: e.target.value }))} placeholder="Ex: LayoutDashboard" />
                <div className="sm:col-span-2">
                  <Select
                    label="Módulo Pai"
                    options={parentOptions}
                    value={form.id_parent}
                    onChange={v => setForm(f => ({ ...f, id_parent: v as number | null }))}
                    placeholder="Nenhum (este é um módulo pai)"
                  />
                </div>
                <FormField label="Ordem" type="number" value={form.order_by} onChange={e => setForm(f => ({ ...f, order_by: e.target.value }))} min={1} />
                <FormField label="Ações (separadas por vírgula)" value={form.actions} onChange={e => setForm(f => ({ ...f, actions: e.target.value }))} placeholder="view,create,edit,delete" />
                <div className="sm:col-span-2 flex flex-col sm:flex-row gap-5 pt-2">
                  <Switch
                    label="Exibir no menu"
                    description="Aparece na barra lateral"
                    checked={form.show_in_menu === 1}
                    onChange={v => setForm(f => ({ ...f, show_in_menu: v ? 1 : 0 }))}
                  />
                  <Switch
                    label="Status"
                    description="Módulo ativo no sistema"
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
          <button type="button" onClick={() => navigate('/administration/modules')} className="w-full sm:w-auto px-6 py-3 text-sm font-medium text-navy-300 hover:text-white border border-navy-700 hover:border-navy-500 rounded-lg transition-colors">
            Cancelar
          </button>
          <button type="submit" disabled={saving} className="w-full sm:w-auto px-8 py-3 bg-navy-600 hover:bg-navy-500 disabled:opacity-50 text-white text-sm font-semibold rounded-lg transition-colors">
            {saving ? 'Salvando...' : isEdit ? 'Salvar alterações' : 'Cadastrar módulo'}
          </button>
        </div>
      </form>
    </Layout>
  )
}
