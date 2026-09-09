import { Navigate, Route, Routes } from 'react-router-dom';
import { useAuth } from '@/api/auth';
import type { Permission } from '@/api/types';
import { AppShell } from '@/shell/AppShell';
import { Approvals } from '@/pages/Approvals';
import { Dashboard } from '@/pages/Dashboard';
import { Employees } from '@/pages/Employees';
import { DesignSystem } from '@/pages/DesignSystem';
import { Finance } from '@/pages/Finance';
import { Help } from '@/pages/Help';
import { Journal } from '@/pages/Journal';
import { Login } from '@/pages/Login';
import { NotFound } from '@/pages/NotFound';
import { Projects } from '@/pages/Projects';
import { Reports } from '@/pages/Reports';
import { Requests } from '@/pages/Requests';
import { RequestForm } from '@/pages/RequestForm';
import { RequestPage } from '@/pages/RequestPage';
import { Settings } from '@/pages/Settings';
import { Sourcing } from '@/pages/Sourcing';
import { Team } from '@/pages/Team';
import type { ReactElement } from 'react';

/** Раздел, закрытый правом. Сервер проверяет то же самое — это только UI. */
function Guarded({ need, children }: { need: Permission; children: ReactElement }) {
  const { can } = useAuth();
  return can(need) ? children : <Navigate to="/" replace />;
}

export function App() {
  const { user, isLoading, failure, retry } = useAuth();

  // Пока не знаем, вошёл ли пользователь, экран входа показывать нельзя:
  // иначе он мигает при каждой перезагрузке страницы.
  if (isLoading) {
    return (
      <div style={{ minHeight: '100vh', display: 'grid', placeItems: 'center' }}>
        <span className="label">ЗАГРУЗКА</span>
      </div>
    );
  }

  // Сервер недоступен — это не «вы вышли». Форма входа здесь только
  // запутает: пароль введут, и он не поможет.
  if (failure) {
    return (
      <main style={{ minHeight: '100vh', display: 'grid', placeItems: 'center', padding: 16 }}>
        <div className="card" style={{ maxWidth: 420, textAlign: 'center' }}>
          <div className="accent-rule" />
          <h1 className="h3" style={{ marginBottom: 4 }}>
            Сервер не отвечает
          </h1>
          <p className="caption" style={{ margin: '0 0 24px' }}>
            {failure instanceof Error ? failure.message : 'Не удалось связаться с сервером'}
            . Проверьте подключение и повторите. Если не проходит — сообщите
            администратору системы.
          </p>
          <button type="button" className="btn btn-primary" onClick={retry}>
            Повторить
          </button>
        </div>
      </main>
    );
  }

  if (!user) {
    return <Login />;
  }

  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<Dashboard />} />
        <Route path="requests" element={<Requests />} />
        <Route path="requests/new" element={<RequestForm />} />
        <Route path="requests/:id" element={<RequestPage />} />
        <Route path="requests/:id/edit" element={<RequestForm />} />
        <Route
          path="approvals"
          element={
            <Guarded need="decide_request">
              <Approvals />
            </Guarded>
          }
        />
        <Route
          path="sourcing"
          element={
            <Guarded need="source_request">
              <Sourcing />
            </Guarded>
          }
        />
        <Route
          path="reports"
          element={
            <Guarded need="view_reports">
              <Reports />
            </Guarded>
          }
        />
        <Route
          path="team"
          element={
            <Guarded need="view_reports">
              <Team />
            </Guarded>
          }
        />
        <Route
          path="finance"
          element={
            <Guarded need="view_reports">
              <Finance />
            </Guarded>
          }
        />
        <Route
          path="employees"
          element={
            <Guarded need="manage_reference">
              <Employees />
            </Guarded>
          }
        />
        <Route
          path="projects"
          element={
            <Guarded need="manage_reference">
              <Projects />
            </Guarded>
          }
        />
        <Route
          path="journal"
          element={
            <Guarded need="view_audit">
              <Journal />
            </Guarded>
          }
        />
        <Route path="settings" element={<Settings />} />
        <Route path="help" element={<Help />} />
        <Route path="system" element={<DesignSystem />} />
        <Route path="dashboard" element={<Navigate to="/" replace />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
