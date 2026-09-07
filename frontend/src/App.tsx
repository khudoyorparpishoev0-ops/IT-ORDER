import { Navigate, Route, Routes } from 'react-router-dom';
import { useAuth } from '@/api/auth';
import type { Permission } from '@/api/types';
import { AppShell } from '@/shell/AppShell';
import { Approvals } from '@/pages/Approvals';
import { Dashboard } from '@/pages/Dashboard';
import { DesignSystem } from '@/pages/DesignSystem';
import { Finance } from '@/pages/Finance';
import { Help } from '@/pages/Help';
import { Login } from '@/pages/Login';
import { NotFound } from '@/pages/NotFound';
import { Reports } from '@/pages/Reports';
import { Requests } from '@/pages/Requests';
import { Settings } from '@/pages/Settings';
import { Team } from '@/pages/Team';
import type { ReactElement } from 'react';

/** Раздел, закрытый правом. Сервер проверяет то же самое — это только UI. */
function Guarded({ need, children }: { need: Permission; children: ReactElement }) {
  const { can } = useAuth();
  return can(need) ? children : <Navigate to="/" replace />;
}

export function App() {
  const { user, isLoading } = useAuth();

  // Пока не знаем, вошёл ли пользователь, экран входа показывать нельзя:
  // иначе он мигает при каждой перезагрузке страницы.
  if (isLoading) {
    return (
      <div style={{ minHeight: '100vh', display: 'grid', placeItems: 'center' }}>
        <span className="label">ЗАГРУЗКА</span>
      </div>
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
        <Route
          path="approvals"
          element={
            <Guarded need="decide_request">
              <Approvals />
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
        <Route path="settings" element={<Settings />} />
        <Route path="help" element={<Help />} />
        <Route path="system" element={<DesignSystem />} />
        <Route path="dashboard" element={<Navigate to="/" replace />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
