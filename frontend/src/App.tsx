import { Navigate, Route, Routes } from 'react-router-dom';
import { AppShell } from '@/shell/AppShell';
import { Approvals } from '@/pages/Approvals';
import { Dashboard } from '@/pages/Dashboard';
import { DesignSystem } from '@/pages/DesignSystem';
import { Finance } from '@/pages/Finance';
import { Help } from '@/pages/Help';
import { NotFound } from '@/pages/NotFound';
import { Reports } from '@/pages/Reports';
import { Requests } from '@/pages/Requests';
import { Settings } from '@/pages/Settings';
import { Team } from '@/pages/Team';

export function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<Dashboard />} />
        <Route path="requests" element={<Requests />} />
        <Route path="approvals" element={<Approvals />} />
        <Route path="reports" element={<Reports />} />
        <Route path="team" element={<Team />} />
        <Route path="finance" element={<Finance />} />
        <Route path="settings" element={<Settings />} />
        <Route path="help" element={<Help />} />
        <Route path="system" element={<DesignSystem />} />
        <Route path="dashboard" element={<Navigate to="/" replace />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
