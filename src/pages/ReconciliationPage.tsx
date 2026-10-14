import { useState, useEffect, useCallback, useRef } from 'react';
import { Button } from '@/components/ui/button';
import Icon from '@/components/ui/icon';
import { useToast } from '@/hooks/use-toast';
import { useAuth } from '@/contexts/AuthContext';
import ReconciliationPeriodPicker from '@/components/reconciliation/ReconciliationPeriodPicker';
import ReconciliationTiles from '@/components/reconciliation/ReconciliationTiles';
import ReconciliationChart from '@/components/reconciliation/ReconciliationChart';
import ReconciliationStatus, { StatusSummary } from '@/components/reconciliation/ReconciliationStatus';
import ReconciliationByProvider from '@/components/reconciliation/ReconciliationByProvider';
import { TypeFilterKey } from '@/lib/transactionTypeFilter';
import functionUrls from '../../backend/func2url.json';
import { resyncGateway } from '@/lib/gatewayResync';

interface ReconciliationTotals {
  payments: { amount: number; count: number };
  receipts: { amount: number; count: number };
  bank: { amount: number; raw_amount: number; commission_amount: number; count: number };
}

interface DailyPoint {
  date: string;
  payments: number;
  receipts: number;
  bank: number;
}

interface ReconciliationResponse {
  success: boolean;
  totals: ReconciliationTotals;
  daily: DailyPoint[];
  details: {
    bank_commission_note: string | null;
    payments_by_provider?: Record<string, { amount: number; count: number; commission?: number }>;
  };
}

const toDateParam = (d: Date) => {
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
};

const getYesterday = () => {
  const d = new Date();
  d.setDate(d.getDate() - 1);
  d.setHours(0, 0, 0, 0);
  return d;
};

const getDefaultFrom = () => {
  const d = getYesterday();
  d.setDate(d.getDate() - 6);
  return d;
};

interface ReconciliationPageProps {
  onOpenTransactions?: (from: Date, to: Date, typeKey?: TypeFilterKey, unmatchedOnly?: boolean) => void;
  onConnectIntegration?: (categorySlug: string) => void;
}

const ReconciliationPage = ({ onOpenTransactions, onConnectIntegration }: ReconciliationPageProps) => {
  const [dateFrom, setDateFrom] = useState<Date>(getDefaultFrom());
  const [dateTo, setDateTo] = useState<Date>(getYesterday());
  const [data, setData] = useState<ReconciliationResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [statusSummary, setStatusSummary] = useState<StatusSummary | null>(null);
  const [isStatusLoading, setIsStatusLoading] = useState(true);
  const { toast } = useToast();
  const { currentCompany, cronEnabled } = useAuth();
  const companyId = currentCompany?.id;
  const [connectedCategories, setConnectedCategories] = useState<Set<string> | null>(null);

  useEffect(() => {
    if (!companyId) return;
    let cancelled = false;
    fetch(`${functionUrls['integrations-list']}?company_id=${companyId}`)
      .then((r) => r.json())
      .then((d) => {
        if (cancelled) return;
        const list: { category_slug?: string }[] = d?.user_integrations || [];
        setConnectedCategories(new Set(list.map((i) => i.category_slug || '').filter(Boolean)));
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [companyId]);

  const tileLocked = (categorySlug: string, count: number) =>
    !!connectedCategories && !connectedCategories.has(categorySlug) && count === 0;

  const statsRequestRef = useRef(0);
  const fetchStats = useCallback(async () => {
    if (!companyId) return;
    const requestId = ++statsRequestRef.current;
    const isStale = () => requestId !== statsRequestRef.current;
    setIsLoading(true);
    try {
      const params = new URLSearchParams({
        company_id: String(companyId),
        date_from: toDateParam(dateFrom),
        date_to: toDateParam(dateTo)
      });
      const response = await fetch(`${functionUrls['reconciliation-stats']}?${params.toString()}`);
      const result = await response.json().catch(() => ({}));
      if (isStale()) return;

      if (response.ok && result.success) {
        setData(result);
      } else {
        toast({
          title: 'Ошибка загрузки',
          description: result.error || 'Не удалось загрузить данные сверки',
          variant: 'destructive'
        });
      }
    } catch (error) {
      if (isStale()) return;
      toast({
        title: 'Ошибка подключения',
        description: 'Проверьте интернет-соединение',
        variant: 'destructive'
      });
    } finally {
      if (!isStale()) setIsLoading(false);
    }
  }, [companyId, dateFrom, dateTo, toast]);

  useEffect(() => {
    if (!companyId) return;

    resyncGateway(companyId, cronEnabled).then((changed) => {
      if (changed) {
        fetchStats();
        fetchStatus();
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [companyId]);

  const fetchStatus = useCallback(async () => {
    if (!companyId) return;
    setIsStatusLoading(true);
    try {
      const params = new URLSearchParams({
        company_id: String(companyId),
        paged: '1',
        status_summary: '1',
        date_from: toDateParam(dateFrom),
        date_to: toDateParam(dateTo)
      });
      const response = await fetch(`${functionUrls['transactions-list']}?${params.toString()}`);
      const result = await response.json();
      setStatusSummary(response.ok && result.summary ? result.summary : null);
    } catch {
      setStatusSummary(null);
    } finally {
      setIsStatusLoading(false);
    }
  }, [companyId, dateFrom, dateTo]);

  useEffect(() => {
    fetchStats();
    fetchStatus();
  }, [fetchStats, fetchStatus]);

  const handlePeriodChange = (from: Date, to: Date) => {
    setDateFrom(from);
    setDateTo(to);
  };

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="flex items-center justify-between gap-3 mb-2">
            <h2 className="text-2xl sm:text-3xl font-display font-bold text-foreground">Сверка</h2>
            <Button
              onClick={() => { fetchStats(); fetchStatus(); }}
              variant="outline"
              size="icon"
              className="sm:hidden shrink-0"
              disabled={isLoading}
              aria-label="Обновить"
              title="Обновить"
            >
              <Icon name="RefreshCw" size={16} className={isLoading ? 'animate-spin' : ''} />
            </Button>
          </div>
          <p className="text-muted-foreground">
            Автоматическая сверка платежей, чеков и поступлений на расчётный счёт
          </p>
        </div>
        <Button onClick={() => { fetchStats(); fetchStatus(); }} variant="outline" disabled={isLoading} className="hidden sm:inline-flex shrink-0">
          <Icon name="RefreshCw" size={16} className={`mr-2 ${isLoading ? 'animate-spin' : ''}`} />
          Обновить
        </Button>
      </div>

      <ReconciliationPeriodPicker dateFrom={dateFrom} dateTo={dateTo} onChange={handlePeriodChange} />

      {isLoading && !data ? (
        <div className="flex items-center justify-center h-64">
          <div className="text-center">
            <Icon name="Loader2" className="animate-spin mx-auto mb-2" size={32} />
            <p className="text-muted-foreground">Считаем сверку...</p>
          </div>
        </div>
      ) : data ? (
        <>
          <ReconciliationTiles
            totals={data.totals}
            onConnectIntegration={onConnectIntegration}
            lockedTiles={{
              payments: tileLocked('payments', data.totals.payments.count),
              receipts: tileLocked('cash_registers', data.totals.receipts.count),
              money: tileLocked('banks', data.totals.bank.count)
            }}
            onTileClick={onOpenTransactions ? (typeKey) => onOpenTransactions(dateFrom, dateTo, typeKey) : undefined}
          />
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
            <ReconciliationChart
              daily={data.daily}
              onDayClick={
                onOpenTransactions
                  ? (day) => {
                      const [y, m, d] = day.split('-').map(Number);
                      const date = new Date(y, m - 1, d);
                      onOpenTransactions(date, date);
                    }
                  : undefined
              }
            />
            <ReconciliationStatus
              summary={statusSummary}
              isLoading={isStatusLoading}
              onOpenUnmatched={onOpenTransactions ? () => onOpenTransactions(dateFrom, dateTo, undefined, true) : undefined}
            />
          </div>
          {data.details.payments_by_provider && (
            <ReconciliationByProvider paymentsByProvider={data.details.payments_by_provider} />
          )}
          {data.details.bank_commission_note && (
            <div className="flex items-start gap-2 text-sm text-muted-foreground bg-muted/50 rounded-lg p-4">
              <Icon name="Info" size={16} className="mt-0.5 shrink-0" />
              <p>{data.details.bank_commission_note}</p>
            </div>
          )}
        </>
      ) : null}
    </div>
  );
};

export default ReconciliationPage;