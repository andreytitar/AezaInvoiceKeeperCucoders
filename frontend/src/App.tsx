import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { Layout } from './components/Layout'
import { Loading } from './components/ui'
import { AuditPage } from './pages/AuditPage'
import { BudgetPage } from './pages/BudgetPage'
import { CalendarPage } from './pages/CalendarPage'
import { DashboardPage } from './pages/DashboardPage'
import { LoginPage } from './pages/LoginPage'
import { RecurringPaymentsPage } from './pages/RecurringPaymentsPage'
import { UsersPage } from './pages/UsersPage'
import { WebhooksPage } from './pages/WebhooksPage'
import { AuthProvider, useAuth } from './store/auth'
import { ToastProvider } from './store/toast'

function Protected({ admin = false, children }: { admin?: boolean; children: React.ReactNode }) {
  const { me, loading, isAdmin } = useAuth()
  if (loading) return <Loading />
  if (!me) return <Navigate to="/login" replace />
  if (admin && !isAdmin) return <Navigate to="/" replace />
  return <>{children}</>
}

export default function App() {
  return (
    <ToastProvider>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route
              element={
                <Protected>
                  <Layout />
                </Protected>
              }
            >
              <Route index element={<DashboardPage />} />
              <Route path="calendar" element={<CalendarPage />} />
              <Route path="budget" element={<BudgetPage />} />
              <Route path="recurring" element={<Protected admin><RecurringPaymentsPage /></Protected>} />
              <Route path="users" element={<Protected admin><UsersPage /></Protected>} />
              <Route path="audit" element={<Protected admin><AuditPage /></Protected>} />
              <Route path="webhooks" element={<Protected admin><WebhooksPage /></Protected>} />
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </ToastProvider>
  )
}
