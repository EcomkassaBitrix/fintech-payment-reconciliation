import { useState, useEffect } from 'react';
import { useToast } from '@/hooks/use-toast';
import { useAuth } from '@/contexts/AuthContext';
import { formatDateOnly, DEFAULT_TIMEZONE } from '@/lib/formatDate';
import functionUrls from '../../../backend/func2url.json';
import { Category, Provider, UserIntegration } from './integrationsPageTypes';

export const useIntegrationsPageData = () => {
  const [categories, setCategories] = useState<Category[]>([]);
  const [userIntegrations, setUserIntegrations] = useState<UserIntegration[]>([]);
  const [hiddenIntegrations, setHiddenIntegrations] = useState<UserIntegration[]>([]);
  const [allProviders, setAllProviders] = useState<Provider[]>([]);
  const [editingIntegration, setEditingIntegration] = useState<UserIntegration | null>(null);
  const [deletingIntegration, setDeletingIntegration] = useState<UserIntegration | null>(null);
  const [showAddDialog, setShowAddDialog] = useState(false);
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [loadingReceipts, setLoadingReceipts] = useState<number | null>(null);
  const [loadingStatement, setLoadingStatement] = useState<number | null>(null);
  const [expandedIds, setExpandedIds] = useState<Set<number>>(new Set());
  const { toast } = useToast();
  const { currentCompany } = useAuth();
  const companyId = currentCompany?.id;

  const fetchIntegrations = async () => {
    if (!companyId) return;
    setIsLoading(true);
    try {
      const response = await fetch(`${functionUrls['integrations-list']}?company_id=${companyId}&include_hidden=1`);
      const data = await response.json();

      if (response.ok) {
        setCategories(data.categories || []);
        const all: UserIntegration[] = data.user_integrations || [];
        setUserIntegrations(all.filter((ui) => ui.status !== 'hidden'));
        setHiddenIntegrations(all.filter((ui) => ui.status === 'hidden'));

        const providers: Provider[] = [];
        (data.categories || []).forEach((cat: Category) => {
          providers.push(...cat.providers);
        });
        setAllProviders(providers);
      } else {
        toast({
          title: 'Ошибка загрузки',
          description: data.error || 'Не удалось загрузить интеграции',
          variant: 'destructive'
        });
      }
    } catch (error) {
      toast({
        title: 'Ошибка подключения',
        description: 'Проверьте интернет-соединение',
        variant: 'destructive'
      });
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchIntegrations();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [companyId]);

  const toggleExpand = (id: number) => {
    setExpandedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const handleAddNew = () => {
    setEditingIntegration(null);
    setShowAddDialog(true);
  };

  const handleEdit = (integration: UserIntegration) => {
    setEditingIntegration(integration);
    setShowAddDialog(true);
  };

  const handleDeleteClick = (integration: UserIntegration) => {
    setDeletingIntegration(integration);
    setShowDeleteDialog(true);
  };

  const handleDeleteConfirm = async () => {
    if (!deletingIntegration) return;

    try {
      const response = await fetch(functionUrls['integrations-delete'], {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ integration_id: deletingIntegration.id, company_id: companyId })
      });

      const data = await response.json();

      if (response.ok && data.success) {
        toast({ title: 'Интеграция удалена' });
        fetchIntegrations();
        setShowDeleteDialog(false);
        setDeletingIntegration(null);
      } else {
        toast({
          title: 'Ошибка',
          description: data.error || 'Не удалось удалить',
          variant: 'destructive'
        });
      }
    } catch (error) {
      toast({
        title: 'Ошибка подключения',
        variant: 'destructive'
      });
    }
  };

  const [togglingId, setTogglingId] = useState<number | null>(null);

  const handleToggleActive = async (integration: UserIntegration, active: boolean) => {
    if (!companyId) return;
    const status = active ? 'active' : 'inactive';
    setTogglingId(integration.id);
    setUserIntegrations((prev) => prev.map((i) => (i.id === integration.id ? { ...i, status } : i)));
    try {
      const res = await fetch(functionUrls['integrations-update'], {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ integration_id: integration.id, company_id: companyId, status })
      });
      if (!res.ok) throw new Error();
      toast({
        title: active ? 'Интеграция включена' : 'Интеграция выключена',
        description: active ? undefined : 'Вебхуки и синхронизация по ней не принимаются, пока не включите'
      });
    } catch {
      setUserIntegrations((prev) => prev.map((i) => (i.id === integration.id ? { ...i, status: integration.status } : i)));
      toast({ title: 'Не удалось переключить', description: 'Попробуйте ещё раз', variant: 'destructive' });
    } finally {
      setTogglingId(null);
    }
  };

  const handleEnableReceipts = async (integration: UserIntegration) => {
    const scenario = integration.stopped_receipt_scenario;
    if (!companyId || !scenario) return;
    setTogglingId(integration.id);
    try {
      const res = await fetch(functionUrls['automation-scenarios'], {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: scenario.id, company_id: companyId, status: 'active' })
      });
      if (!res.ok) throw new Error();
      setUserIntegrations((prev) =>
        prev.map((i) => (i.id === integration.id ? { ...i, receipts_enabled: true, stopped_receipt_scenario: null } : i))
      );
      toast({ title: `Автоматизация «${scenario.name}» включена`, description: 'Чеки создаются' });
    } catch {
      toast({ title: 'Не удалось включить автоматизацию', description: 'Попробуйте ещё раз', variant: 'destructive' });
    } finally {
      setTogglingId(null);
    }
  };

  const copyWebhookUrl = (token: string) => {
    const url = `${functionUrls['webhook-receive']}?token=${token}`;
    navigator.clipboard.writeText(url);
    toast({
      title: 'Скопировано',
      description: 'URL вебхука скопирован в буфер обмена'
    });
  };

  const timezone = currentCompany?.timezone || DEFAULT_TIMEZONE;

  const plural = (n: number, one: string, few: string, many: string) => {
    const m10 = n % 10;
    const m100 = n % 100;
    if (m10 === 1 && m100 !== 11) return one;
    if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return few;
    return many;
  };

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return 'Никогда';
    const date = new Date(dateStr);
    const now = new Date();
    const diff = now.getTime() - date.getTime();
    const minutes = Math.floor(diff / 60000);
    const hours = Math.floor(diff / 3600000);
    const days = Math.floor(diff / 86400000);

    if (minutes < 1) return 'Только что';
    if (minutes < 60) return `${minutes} ${plural(minutes, 'минуту', 'минуты', 'минут')} назад`;
    if (hours < 24) return `${hours} ${plural(hours, 'час', 'часа', 'часов')} назад`;
    if (days < 7) return `${days} ${plural(days, 'день', 'дня', 'дней')} назад`;
    return formatDateOnly(dateStr, timezone);
  };

  const handleFetchReceipts = async (integrationId: number, days: number) => {
    setLoadingReceipts(integrationId);

    const dateTo = new Date();
    const dateFrom = new Date();
    dateFrom.setDate(dateFrom.getDate() - days);

    try {
      const response = await fetch(functionUrls['ofd-fetch-receipts'], {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          integration_id: integrationId,
          date_from: dateFrom.toISOString(),
          date_to: dateTo.toISOString()
        })
      });

      const data = await response.json();

      if (response.ok && data.success) {
        const periodLabel = days === 1 ? 'за вчера' : `за последние ${days} дней`;
        toast({
          title: 'Чеки загружены',
          description: `Загружено ${data.inserted} из ${data.total_receipts} чеков ${periodLabel}`
        });
      } else {
        console.error('OFD Error Details:', data);

        const debugInfo = data.debug ?
          `\n\nURL: ${data.debug.full_url}\nAPI: ${data.debug.api_url}\nПериод: ${data.debug.date_from} - ${data.debug.date_to}` : '';

        toast({
          title: 'Ошибка загрузки',
          description: (data.error || 'Не удалось загрузить чеки') + debugInfo,
          variant: 'destructive',
          duration: 10000
        });
      }
    } catch (error) {
      toast({
        title: 'Ошибка подключения',
        variant: 'destructive'
      });
    } finally {
      setLoadingReceipts(null);
    }
  };

  const handleSyncStatement = async (integrationId: number) => {
    setLoadingStatement(integrationId);

    try {
      const response = await fetch(functionUrls['bank-statement-sync'], {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ integration_id: integrationId })
      });

      const data = await response.json();

      if (response.ok && data.success) {
        toast({
          title: 'Выписка синхронизирована',
          description: `Загружено ${data.inserted} новых операций из ${data.total_transactions}`
        });
      } else {
        toast({
          title: 'Ошибка синхронизации',
          description: data.error || 'Не удалось получить выписку',
          variant: 'destructive'
        });
      }
    } catch (error) {
      toast({
        title: 'Ошибка подключения',
        variant: 'destructive'
      });
    } finally {
      setLoadingStatement(null);
    }
  };

  const getCategoryIntegrations = (categorySlug: string) => {
    return userIntegrations.filter(ui => ui.category_slug === categorySlug);
  };

  return {
    hiddenIntegrations,
    categories,
    userIntegrations,
    allProviders,
    editingIntegration,
    deletingIntegration,
    showAddDialog,
    setShowAddDialog,
    showDeleteDialog,
    setShowDeleteDialog,
    isLoading,
    loadingReceipts,
    loadingStatement,
    expandedIds,
    companyId,
    fetchIntegrations,
    toggleExpand,
    handleAddNew,
    handleEdit,
    handleDeleteClick,
    handleDeleteConfirm,
    copyWebhookUrl,
    formatDate,
    handleFetchReceipts,
    handleSyncStatement,
    handleToggleActive,
    handleEnableReceipts,
    togglingId,
    getCategoryIntegrations
  };
};