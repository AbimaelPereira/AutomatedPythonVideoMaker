import { Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider, useAuth } from './contexts/AuthContext'
import { ToastProvider } from './contexts/ToastContext'
import LoginPage from './pages/auth/LoginPage'
import DashboardPage from './pages/dashboard/DashboardPage'
import UsersPage from './pages/administration/users/UsersPage'
import UserFormPage from './pages/administration/users/UserFormPage'
import GroupsPage from './pages/administration/groups/GroupsPage'
import GroupFormPage from './pages/administration/groups/GroupFormPage'
import ModulesPage from './pages/administration/modules/ModulesPage'
import ModuleFormPage from './pages/administration/modules/ModuleFormPage'
import RemoteAssetsPage from './pages/remote-assets/RemoteAssetsPage'
import RemoteAssetFormPage from './pages/remote-assets/RemoteAssetFormPage'
import RemoteAssetDetailPage from './pages/remote-assets/RemoteAssetDetailPage'
import ReelsCutterPage from './pages/reelscutter/ReelsCutterPage'
import LandingPage from './pages/landing/LandingPage'

const Spinner = () => (
  <div className="flex h-screen items-center justify-center" style={{ background: '#0d1117' }}>
    <span className="w-6 h-6 border-2 border-navy-500 border-t-transparent rounded-full animate-spin" />
  </div>
)

function RotaProtegida({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth()
  if (loading) return <Spinner />
  if (!user) return <Navigate to="/login" replace />
  return <>{children}</>
}

function RotaPublica({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth()
  if (loading) return <Spinner />
  if (user) return <Navigate to="/dashboard" replace />
  return <>{children}</>
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/login" element={<RotaPublica><LoginPage /></RotaPublica>} />
      <Route path="/dashboard" element={<RotaProtegida><DashboardPage /></RotaProtegida>} />
      <Route path="/administration/users" element={<RotaProtegida><UsersPage /></RotaProtegida>} />
      <Route path="/administration/users/:id" element={<RotaProtegida><UserFormPage /></RotaProtegida>} />
      <Route path="/administration/groups" element={<RotaProtegida><GroupsPage /></RotaProtegida>} />
      <Route path="/administration/groups/:id" element={<RotaProtegida><GroupFormPage /></RotaProtegida>} />
      <Route path="/administration/modules" element={<RotaProtegida><ModulesPage /></RotaProtegida>} />
      <Route path="/administration/modules/:id" element={<RotaProtegida><ModuleFormPage /></RotaProtegida>} />
      <Route path="/remote-assets/assets" element={<RotaProtegida><RemoteAssetsPage /></RotaProtegida>} />
      <Route path="/remote-assets/assets/new" element={<RotaProtegida><RemoteAssetFormPage /></RotaProtegida>} />
      <Route path="/remote-assets/assets/:id/edit" element={<RotaProtegida><RemoteAssetFormPage /></RotaProtegida>} />
      <Route path="/remote-assets/assets/:id" element={<RotaProtegida><RemoteAssetDetailPage /></RotaProtegida>} />
      <Route path="/reelscutter" element={<RotaProtegida><ReelsCutterPage /></RotaProtegida>} />
    </Routes>
  )
}

export default function App() {
  return (
    <ToastProvider>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </ToastProvider>
  )
}
