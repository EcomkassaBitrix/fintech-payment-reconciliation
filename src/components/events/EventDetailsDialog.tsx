import { transactionStatusLabel } from '@/lib/transactionStatus';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import Icon from '@/components/ui/icon';
import { AppEvent, EVENT_ORIGIN_LABELS } from './eventsTypes';
import { useAuth } from '@/contexts/AuthContext';
import { formatDateTime, DEFAULT_TIMEZONE } from '@/lib/formatDate';
import { transactionTypeConfig } from './EventsTable';
import { ofdFnsStatusLabel, ofdFnsStatusColorClass } from '@/lib/ofdFnsStatus';
import PendingInvoiceCheck from './PendingInvoiceCheck';

interface EventDetailsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  event: AppEvent | null;
}

const getStatusColor = (status: string | null) => {
  switch (status) {
    case 'CONFIRMED':
    case 'processed':
      return 'bg-success';
    case 'AUTHORIZED':
      return 'bg-info';
    case 'OFFSET':
      return 'bg-primary';
    case 'REJECTED':
    case 'failed':
    case 'rejected':
      return 'bg-destructive';
    case 'REFUNDED':
      return 'bg-warning';
    case 'CANCELED':
      return 'bg-muted-foreground';
    default:
      return 'bg-muted-foreground';
  }
};

// У чеков ОФД status - это FnsStatus (статус пробития в налоговой), не
// платёжный статус - см. тот же комментарий в EventsTable.tsx.
const getStatusDisplay = (event: Pick<AppEvent, 'provider_slug' | 'status'>) => {
  if (event.provider_slug === 'ofdru') {
    return { label: ofdFnsStatusLabel(event.status), color: ofdFnsStatusColorClass(event.status) };
  }
  return { label: transactionStatusLabel(event.status), color: getStatusColor(event.status) };
};

const EventDetailsDialog = ({ open, onOpenChange, event }: EventDetailsDialogProps) => {
  const { currentCompany } = useAuth();
  const timezone = currentCompany?.timezone || DEFAULT_TIMEZONE;
  const formatDate = (dateStr: string | null) => formatDateTime(dateStr, timezone, true);

  if (!event) return null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="h-[100dvh] max-h-[100dvh] w-screen max-w-none content-start overflow-y-auto overflow-x-hidden rounded-none border-0 p-4 sm:h-auto sm:max-h-[90vh] sm:w-[calc(100vw-1.5rem)] sm:max-w-3xl sm:rounded-lg sm:border sm:p-6 [&>*]:min-w-0">
        <DialogHeader className="pr-8 text-left">
          <DialogTitle className="flex items-start gap-2 text-lg leading-snug sm:gap-3 sm:text-xl">
            <Icon name="Radio" size={22} className="mt-0.5 shrink-0" />
            <span className="min-w-0 break-words [overflow-wrap:anywhere]">{event.summary}</span>
          </DialogTitle>
          <DialogDescription className="break-words">
            Событие из {event.integration_name} ({event.provider_type})
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-5 sm:space-y-6">
          <div className="grid grid-cols-2 gap-3 sm:gap-4">
            <div className="min-w-0 space-y-1">
              <p className="text-sm text-muted-foreground">Номер события</p>
              <p className="break-all font-mono text-base font-semibold sm:text-lg">{event.event_number || '—'}</p>
            </div>
            <div className="space-y-1">
              <p className="text-sm text-muted-foreground">Статус</p>
              <Badge className={`${getStatusDisplay(event).color} text-white`}>
                {getStatusDisplay(event).label || '—'}
              </Badge>
            </div>
          </div>

          {event.event_type === 'ecomkassa_pending_invoice' && event.event_number && currentCompany?.id && (
            <>
              <Separator />
              <PendingInvoiceCheck key={event.id} companyId={currentCompany.id} invoiceUuid={event.event_number} />
            </>
          )}

          <Separator />

          <div className="space-y-3">
            <h3 className="font-semibold flex items-center gap-2">
              <Icon name="Info" size={18} />
              Информация о событии
            </h3>
            <div className="grid grid-cols-2 gap-x-3 gap-y-4 sm:gap-4 [&>div]:min-w-0">
              <div>
                <p className="text-sm text-muted-foreground">Тип</p>
                <Badge variant="outline" className={`gap-1.5 ${(transactionTypeConfig[event.transaction_type] || transactionTypeConfig.payment).className}`}>
                  <Icon name={(transactionTypeConfig[event.transaction_type] || transactionTypeConfig.payment).icon as any} size={12} />
                  {(transactionTypeConfig[event.transaction_type] || transactionTypeConfig.payment).label}
                </Badge>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Тип интеграции</p>
                <p className="break-words text-sm">{event.provider_type}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Интеграция</p>
                <p className="break-words text-sm">{event.integration_name}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Дата и время</p>
                <p className="text-sm">{formatDate(event.created_at)}</p>
              </div>
              {event.event_type && (
                <div>
                  <p className="text-sm text-muted-foreground">Тип события</p>
                  <p className="break-all font-mono text-sm">{event.event_type}</p>
                </div>
              )}
              {event.origin && EVENT_ORIGIN_LABELS[event.origin] && (
                <div className="col-span-2 sm:col-span-1">
                  <p className="text-sm text-muted-foreground">Источник</p>
                  <p className="text-sm flex items-center gap-1.5" title={EVENT_ORIGIN_LABELS[event.origin].hint}>
                    <Icon name={EVENT_ORIGIN_LABELS[event.origin].icon} fallback="Info" size={14} className="text-muted-foreground" />
                    {EVENT_ORIGIN_LABELS[event.origin].label}
                  </p>
                  <p className="text-xs text-muted-foreground mt-0.5">{EVENT_ORIGIN_LABELS[event.origin].hint}</p>
                </div>
              )}
            </div>
          </div>

          {event.error_message && (
            <div className="p-3 bg-destructive/10 rounded-md">
              <div className="flex items-start gap-2">
                <Icon name="AlertCircle" size={16} className="text-destructive mt-0.5 shrink-0" />
                <div className="min-w-0">
                  <div className="font-medium text-sm text-destructive mb-1">Ошибка обработки</div>
                  <div className="break-words text-xs text-muted-foreground [overflow-wrap:anywhere]">{event.error_message}</div>
                </div>
              </div>
            </div>
          )}

          <Separator />

          <div className="space-y-3">
            <h3 className="font-semibold flex items-center gap-2">
              <Icon name="Code" size={18} />
              Данные события (raw JSON)
            </h3>
            <div className="bg-muted p-3 rounded-lg overflow-x-auto sm:p-4">
              <pre className="text-[11px] font-mono whitespace-pre-wrap break-words [overflow-wrap:anywhere] sm:text-xs">
                {JSON.stringify(event.raw, null, 2)}
              </pre>
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
};

export default EventDetailsDialog;