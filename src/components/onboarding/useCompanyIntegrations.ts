import { useCallback, useEffect, useState } from 'react';
import { UserIntegration } from '@/components/integrations/integrationsPageTypes';
import functionUrls from '../../../backend/func2url.json';

export const useCompanyIntegrations = (companyId?: number) => {
  const [items, setItems] = useState<UserIntegration[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  const reload = useCallback(async () => {
    if (!companyId) return;
    setIsLoading(true);
    try {
      const res = await fetch(`${functionUrls['integrations-list']}?company_id=${companyId}`);
      const data = await res.json();
      if (res.ok) setItems((data.user_integrations || []).filter((i: UserIntegration) => i.status !== 'hidden'));
    } finally {
      setIsLoading(false);
    }
  }, [companyId]);

  useEffect(() => {
    reload();
  }, [reload]);

  return { items, isLoading, reload };
};
