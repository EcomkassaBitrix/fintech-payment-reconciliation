import { ReactNode, useEffect, useState } from 'react';
import { useLocation } from "@/lib/router-compat";
import { useAuth } from '@/contexts/AuthContext';
import MaintenancePage from '@/pages/MaintenancePage';
import functionUrls from '../../backend/func2url.json';

interface Maintenance {
  enabled: boolean;
  message: string | null;
  until: string | null;
}

// Вход и админка открыты всегда - чтобы администратор мог зайти и выключить режим.
const ALWAYS_OPEN = ['/login', '/admin', '/oauth/tochka'];

const MaintenanceGate = ({ children }: { children: ReactNode }) => {
  const location = useLocation();
  const { isPlatformAdmin, isLoading } = useAuth();
  const [maintenance, setMaintenance] = useState<Maintenance | null>(null);

  useEffect(() => {
    fetch(`${(functionUrls as Record<string, string>)['platform-settings']}?public=1`)
      .then((r) => r.json())
      .then((data) => setMaintenance(data.maintenance || null))
      .catch(() => setMaintenance(null));
  }, []);

  const preview = new URLSearchParams(location.search).get('maintenance_preview') === '1';
  if (preview) {
    return <MaintenancePage message={maintenance?.message} until={maintenance?.until} />;
  }

  const blocked = maintenance?.enabled
    && !isLoading
    && !isPlatformAdmin
    && !ALWAYS_OPEN.some((p) => location.pathname.startsWith(p));

  if (blocked) {
    return <MaintenancePage message={maintenance?.message} until={maintenance?.until} />;
  }
  return <>{children}</>;
};

export default MaintenanceGate;
