import { useState, useEffect, useRef } from 'react';
import { format } from 'date-fns';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import Icon from '@/components/ui/icon';
import { useToast } from '@/hooks/use-toast';
import { useAuth } from '@/contexts/AuthContext';
import EventsTable from '@/components/events/EventsTable';
import EventsFilters from '@/components/events/EventsFilters';
import { DateFilter } from '@/components/filters/DateRangeFilter';
import EventDetailsDialog from '@/components/events/EventDetailsDialog';
import { AppEvent, EventSource } from '@/components/events/eventsTypes';
import functionUrls from '../../backend/func2url.json';
import { resyncGateway } from '@/lib/gatewayResync';
import { useBackfill } from '@/contexts/BackfillContext';
import BackfillDialog from '@/components/transactions/BackfillDialog';
import { ActiveSources, fetchActiveSources } from '@/components/transactions/backfill/backfillSources';

const EventsPage = () => {
  const [backfillSources, setBackfillSources] = useState<ActiveSources>({
    ecomkassa: [], ofd: [], bank: [], acquiring: [], ecomGateway: []
  });
  const { openDialog, completedTick, phase: backfillPhase } = useBackfill();
  const [events, setEvents] = useState<AppEvent[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [selectedEvent, setSelectedEvent] = useState<AppEvent | null>(null);
  const [showDetails, setShowDetails] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [dateFilter, setDateFilter] = useState<DateFilter | null>(null);
  const [sourceFilter, setSourceFilter] = useState<EventSource[]>([]);
  const [errorsOnly, setErrorsOnly] = useState(false);
  const [pendingOnly, setPendingOnly] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const hasLoadedOnce = useRef(false);
  const { toast } = useToast();
  const { currentCompany, cronEnabled } = useAuth();
  const companyId = currentCompany?.id;

  const fetchEvents = async () => {
    if (!companyId) return;
    if (hasLoadedOnce.current) setIsRefreshing(true);
    else setIsLoading(true);
    try {
      const params = new URLSearchParams({ company_id: String(companyId), limit: dateFilter || sourceFilter.length || errorsOnly || pendingOnly ? '2000' : '200' });
      if (errorsOnly) params.set('errors_only', '1');
      if (pendingOnly) params.set('pending_only', '1');
      if (sourceFilter.length) params.set('sources', sourceFilter.join(','));
      if (dateFilter) {
        params.set('date_from', format(dateFilter.from, 'yyyy-MM-dd'));
        params.set('date_to', format(dateFilter.to, 'yyyy-MM-dd'));
      }
      const response = await fetch(`${functionUrls['events-list']}?${params}`);
      const data = await response.json();

      if (response.ok) {
        setEvents(data.events || []);
      } else {
        toast({
          title: 'Ошибка загрузки',
          description: data.error || 'Не удалось загрузить события',
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
      setIsRefreshing(false);
      hasLoadedOnce.current = true;
    }
  };

  // Список источников для загрузки обновляем перед каждым открытием окна,
  // чтобы только что подключённая касса/банк сразу появились в списке.
  const fetchBackfillSources = () => {
    if (!companyId) return;
    fetchActiveSources(companyId).then(setBackfillSources).catch(() => {});
  };

  const openBackfillDialog = () => {
    fetchBackfillSources();
    openDialog();
  };

  useEffect(() => {
    if (!companyId) return;

    resyncGateway(companyId, cronEnabled).then((changed) => {
      if (changed) {
        fetchEvents();
      }
    });

    fetchBackfillSources();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [companyId]);

  const isFirstCompletedTick = completedTick === 0;
  useEffect(() => {
    if (isFirstCompletedTick) return;
    fetchEvents();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [completedTick]);

  const dateKey = dateFilter ? `${dateFilter.from.toDateString()}-${dateFilter.to.toDateString()}` : '';
  useEffect(() => {
    if (!companyId) return;
    fetchEvents();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [companyId, dateKey, sourceFilter.join(','), errorsOnly, pendingOnly]);

  const handleRowClick = (event: AppEvent) => {
    setSelectedEvent(event);
    setShowDetails(true);
  };

  const filteredEvents = events.filter(event => {
    if (!searchQuery) return true;

    const query = searchQuery.toLowerCase();

    // Ищем не только по номеру события, но и по любым данным внутри
    // присланного вебхука (сумма, email, номер заказа и т.д.) - сериализуем
    // raw в строку и историю повторных хуков, чтобы не плодить ручные проверки
    // под каждое поле у каждого провайдера.
    const haystack = [
      event.event_number,
      event.summary,
      event.integration_name,
      event.payment_provider,
      JSON.stringify(event.raw ?? ''),
      JSON.stringify(event.webhook_history?.map(h => h.raw) ?? '')
    ]
      .join(' ')
      .toLowerCase();

    return haystack.includes(query);
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-96">
        <div className="text-center">
          <Icon name="Loader2" className="animate-spin mx-auto mb-2" size={32} />
          <p className="text-muted-foreground">Загрузка событий...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="flex items-center justify-between gap-3 mb-2">
            <h2 className="text-2xl sm:text-3xl font-display font-bold text-foreground">События</h2>
          </div>
          <p className="text-sm text-muted-foreground sm:text-base">
            Все входящие вебхуки и операции по интеграциям компании
          </p>
        </div>
        <div className="grid grid-cols-[1fr_auto] gap-2 sm:flex sm:items-center shrink-0">
          <Button onClick={openBackfillDialog} variant="outline" className="gap-2">
            <Icon name={backfillPhase === 'running' ? 'Loader2' : 'Download'} size={16} className={backfillPhase === 'running' ? 'animate-spin' : ''} />
            {backfillPhase === 'running' ? 'Загрузка идёт…' : 'Загрузить'}
          </Button>
          <Button onClick={fetchEvents} variant="outline" size="icon" disabled={isRefreshing} aria-label="Обновить" title="Обновить">
            <Icon name="RefreshCw" size={16} className={isRefreshing ? 'animate-spin' : ''} />
          </Button>
        </div>
      </div>

      <Card>
        <CardHeader className="p-4 sm:p-6">
          <CardTitle className="text-xl sm:text-2xl leading-tight">Лента событий</CardTitle>
          <CardDescription>
            Нажмите на событие, чтобы посмотреть его детали
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4 p-3 pt-0 sm:p-6 sm:pt-0">
          <EventsFilters
            searchQuery={searchQuery}
            setSearchQuery={setSearchQuery}
            dateFilter={dateFilter}
            setDateFilter={setDateFilter}
            sourceFilter={sourceFilter}
            setSourceFilter={setSourceFilter}
            errorsOnly={errorsOnly}
            setErrorsOnly={setErrorsOnly}
            pendingOnly={pendingOnly}
            setPendingOnly={setPendingOnly}
          />

          <EventsTable events={filteredEvents} onRowClick={handleRowClick} />
        </CardContent>
      </Card>

      <EventDetailsDialog
        open={showDetails}
        onOpenChange={setShowDetails}
        event={selectedEvent}
      />

      <BackfillDialog sources={backfillSources} />
    </div>
  );
};

export default EventsPage;