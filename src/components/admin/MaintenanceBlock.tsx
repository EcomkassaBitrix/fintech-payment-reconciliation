import { useCallback, useEffect, useState } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import functionUrls from '../../../backend/func2url.json';
import MaintenanceCard from './MaintenanceCard';

const api = (functionUrls as Record<string, string>)['platform-settings'];

interface MaintenanceState {
  maintenance_enabled: boolean;
  maintenance_message: string | null;
  maintenance_until: string | null;
}

const MaintenanceBlock = () => {
  const { user } = useAuth();
  const [state, setState] = useState<MaintenanceState | null>(null);

  const load = useCallback(async () => {
    if (!user) return;
    const res = await fetch(`${api}?requester_user_id=${user.user_id}`);
    const data = await res.json();
    if (res.ok) setState(data.settings);
  }, [user]);

  useEffect(() => {
    load();
  }, [load]);

  if (!state) return null;
  return (
    <MaintenanceCard
      enabled={state.maintenance_enabled}
      message={state.maintenance_message}
      until={state.maintenance_until}
      onSaved={load}
    />
  );
};

export default MaintenanceBlock;
