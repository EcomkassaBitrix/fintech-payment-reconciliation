import { transactionStatusLabel } from '@/lib/transactionStatus';
import React, { useState } from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import Icon from '@/components/ui/icon';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { AppEvent, EventWebhookHistoryItem } from './eventsTypes';
import { useAuth } from '@/contexts/AuthContext';
import { formatDateTime, DEFAULT_TIMEZONE } from '@/lib/formatDate';
import { ofdFnsStatusLabel, ofdFnsStatusColorClass } from '@/lib/ofdFnsStatus';

interface EventsTableProps {
  events: AppEvent[];
  onRowClick: (event: AppEvent) => void;
}

// Унифицированная категория события (как в реестре "Транзакции", см.
// components/transactions/TransactionsTable.tsx typeConfig) - в отличие от
// provider_type (конкретный провайдер вроде "Касса (эквайринг)"), это ответ
// на вопрос "что это за документ" независимо от того, какая интеграция его
// прислала.
export const transactionTypeConfig: Record<string, { icon: string; label: string; className: string }> = {
  payment: { icon: 'CreditCard', label: 'Платёж', className: 'bg-primary/10 text-primary border-primary/30' },
  receipt: { icon: 'Receipt', label: 'Чек', className: 'bg-info/10 text-info border-info/30' },
  receipt_order: { icon: 'Truck', label: 'Заказ', className: 'bg-orange-500/10 text-orange-400 border-orange-500/30' },
  money: { icon: 'Landmark', label: 'Деньги', className: 'bg-success/10 text-success border-success/30' },
  crm: { icon: 'Users', label: 'CRM', className: 'bg-violet-500/10 text-violet-400 border-violet-500/30' },
};

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

// У чеков ОФД status - это FnsStatus (Success/Fail/Wait, статус ПРОБИТИЯ чека
// в налоговой), не платёжный статус вроде CONFIRMED/REJECTED - нужен свой
// лейбл и своя цветовая раскладка (см. lib/ofdFnsStatus.ts), иначе бейдж
// показывал бы сырое "Success" серым цветом по умолчанию.
const getStatusDisplay = (event: Pick<AppEvent, 'provider_slug' | 'status'>) => {
  if (event.provider_slug === 'ofdru') {
    return { label: ofdFnsStatusLabel(event.status), color: ofdFnsStatusColorClass(event.status) };
  }
  return { label: transactionStatusLabel(event.status), color: getStatusColor(event.status) };
};

const EventsTable = ({ events, onRowClick }: EventsTableProps) => {
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set());
  const { currentCompany } = useAuth();
  const timezone = currentCompany?.timezone || DEFAULT_TIMEZONE;
  const formatDate = (dateStr: string | null) => formatDateTime(dateStr, timezone);

  const toggleRowExpand = (eventId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setExpandedRows(prev => {
      const next = new Set(prev);
      if (next.has(eventId)) {
        next.delete(eventId);
      } else {
        next.add(eventId);
      }
      return next;
    });
  };

  const handleHistoryItemClick = (event: AppEvent, historyItem: EventWebhookHistoryItem) => {
    onRowClick({
      ...event,
      status: historyItem.status,
      error_message: historyItem.error_message,
      created_at: historyItem.created_at,
      raw: historyItem.raw,
      event_type: historyItem.event_type
    });
  };

  const sortedHistory = (history: EventWebhookHistoryItem[]) =>
    history.slice().sort((a, b) => new Date(a.created_at || '').getTime() - new Date(b.created_at || '').getTime());

  const mobileList = (
    <div className="space-y-2 md:hidden">
      {events.length === 0 ? (
        <div className="rounded-lg border py-8 text-center text-sm text-muted-foreground">События не найдены</div>
      ) : (
        events.map((event) => {
          const history = event.webhook_history || [];
          const hasHistory = history.length > 1;
          const isExpanded = expandedRows.has(event.id);
          const config = transactionTypeConfig[event.transaction_type] || transactionTypeConfig.payment;
          const st = event.status ? getStatusDisplay(event) : null;
          return (
            <div key={event.id} className="overflow-hidden rounded-lg border border-border">
              <div
                className="cursor-pointer p-3 transition-colors active:bg-muted/50"
                onClick={(e) => (hasHistory ? toggleRowExpand(event.id, e) : onRowClick(event))}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex min-w-0 flex-wrap items-center gap-1.5">
                    <Badge variant="outline" className={`gap-1.5 ${config.className}`}>
                      <Icon name={config.icon as any} size={12} />
                      {config.label}
                    </Badge>
                    {st && <Badge className={`${st.color} text-white`}>{st.label}</Badge>}
                  </div>
                  {hasHistory ? (
                    <span className="inline-flex shrink-0 items-center gap-0.5 text-xs text-muted-foreground">
                      {history.length}
                      <Icon name={isExpanded ? 'ChevronUp' : 'ChevronDown'} size={14} />
                    </span>
                  ) : (
                    <Icon name="ChevronRight" size={16} className="shrink-0 text-muted-foreground" />
                  )}
                </div>
                <div className="mt-1.5 break-words text-sm font-medium [overflow-wrap:anywhere]">{event.integration_name}</div>
                {event.summary && (
                  <div className="break-words text-xs text-muted-foreground [overflow-wrap:anywhere]">{event.summary}</div>
                )}
                <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
                  <span>{formatDate(event.created_at)}</span>
                  {event.event_number && <span className="font-mono">№ {event.event_number}</span>}
                  {event.payment_provider && <Badge variant="secondary" className="text-[11px]">{event.payment_provider}</Badge>}
                  {event.receipt_kind && <Badge variant="secondary" className="text-[11px]">{event.receipt_kind}</Badge>}
                </div>
              </div>
              {hasHistory && isExpanded && (
                <div className="space-y-2 border-t border-border bg-muted/30 p-2">
                  {sortedHistory(history).map((item, idx) => (
                    <button
                      type="button"
                      key={item.id}
                      onClick={() => handleHistoryItemClick(event, item)}
                      className="flex w-full items-start gap-2 rounded-md border border-border bg-background p-2.5 text-left active:bg-muted/50"
                    >
                      <Badge variant="outline" className="shrink-0">{idx + 1}</Badge>
                      <div className="min-w-0 flex-1 space-y-1">
                        <div className="flex flex-wrap items-center gap-1.5">
                          {item.status && (
                            <Badge className={`${getStatusColor(item.status)} text-white`}>{transactionStatusLabel(item.status)}</Badge>
                          )}
                          <span className="text-xs text-muted-foreground">{formatDate(item.created_at)}</span>
                        </div>
                        {item.error_message && (
                          <div className="break-words text-xs text-destructive [overflow-wrap:anywhere]">{item.error_message}</div>
                        )}
                      </div>
                      <Icon name="ChevronRight" size={14} className="mt-1 shrink-0 text-muted-foreground" />
                    </button>
                  ))}
                </div>
              )}
            </div>
          );
        })
      )}
    </div>
  );

  return (
    <>
    {mobileList}
    <div className="hidden border rounded-lg overflow-x-auto md:block">
      <Table className="min-w-[720px]">
        <TableHeader>
          <TableRow>
            <TableHead className="w-[40px]"></TableHead>
            <TableHead>Дата и время</TableHead>
            <TableHead>Интеграция</TableHead>
            <TableHead>Тип</TableHead>
            <TableHead>Номер события</TableHead>
            <TableHead>Статус</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {events.length === 0 ? (
            <TableRow>
              <TableCell colSpan={6} className="text-center py-8 text-muted-foreground">
                События не найдены
              </TableCell>
            </TableRow>
          ) : (
            events.map((event) => {
              const history = event.webhook_history || [];
              const hasHistory = history.length > 1;
              const isExpanded = expandedRows.has(event.id);

              return (
                <React.Fragment key={event.id}>
                  <TableRow
                    className="cursor-pointer hover:bg-muted/50"
                    onClick={(e) => hasHistory ? toggleRowExpand(event.id, e) : onRowClick(event)}
                  >
                    <TableCell>
                      {hasHistory && (
                        <Icon
                          name={isExpanded ? 'ChevronDown' : 'ChevronRight'}
                          size={16}
                          className="text-muted-foreground"
                        />
                      )}
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground whitespace-nowrap">
                      {formatDate(event.created_at)}
                    </TableCell>
                    <TableCell>
                      <div className="text-sm font-medium">{event.integration_name}</div>
                      <div className="max-w-md break-words text-xs text-muted-foreground">{event.summary}</div>
                    </TableCell>
                    <TableCell>
                      {(() => {
                        const config = transactionTypeConfig[event.transaction_type] || transactionTypeConfig.payment;
                        return (
                          <Badge variant="outline" className={`gap-1.5 ${config.className}`}>
                            <Icon name={config.icon as any} size={12} />
                            {config.label}
                          </Badge>
                        );
                      })()}
                      <div className="text-xs text-muted-foreground mt-1">{event.provider_type}</div>
                      {event.payment_provider && (
                        <Badge variant="secondary" className="mt-1">{event.payment_provider}</Badge>
                      )}
                      {event.receipt_kind && (
                        <Badge variant="secondary" className="mt-1">{event.receipt_kind}</Badge>
                      )}
                    </TableCell>
                    <TableCell className="font-mono text-sm">
                      {event.event_number || '—'}
                    </TableCell>
                    <TableCell>
                      {event.status && (
                        <Badge className={`${getStatusDisplay(event).color} text-white`}>
                          {getStatusDisplay(event).label}
                        </Badge>
                      )}
                    </TableCell>
                  </TableRow>

                  {hasHistory && isExpanded && (
                    <TableRow key={`${event.id}-details`}>
                      <TableCell colSpan={6} className="bg-muted/30 p-0">
                        <div className="p-4 space-y-3">
                          <div className="text-sm font-semibold text-muted-foreground mb-3">
                            История вебхуков ({history.length})
                          </div>
                          {history
                            .slice()
                            .sort((a, b) => new Date(a.created_at || '').getTime() - new Date(b.created_at || '').getTime())
                            .map((item, idx) => (
                              <div
                                key={item.id}
                                className="bg-background rounded-lg p-4 border border-border hover:border-primary/50 transition-colors cursor-pointer"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleHistoryItemClick(event, item);
                                }}
                              >
                                <div className="flex items-start justify-between gap-4">
                                  <div className="flex items-start gap-3 flex-1">
                                    <Badge variant="outline" className="mt-0.5 shrink-0">{idx + 1}</Badge>
                                    <div className="flex-1 space-y-2">
                                      <div className="flex items-center gap-2 flex-wrap">
                                        {item.status && (
                                          <Badge className={`${getStatusColor(item.status)} text-white`}>
                                            {item.status}
                                          </Badge>
                                        )}
                                        <span className="text-sm text-muted-foreground">
                                          {formatDate(item.created_at)}
                                        </span>
                                      </div>

                                      <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
                                        <div>
                                          <span className="text-muted-foreground">Webhook ID:</span>{' '}
                                          <span className="font-mono">{item.id}</span>
                                        </div>
                                        {item.error_message && (
                                          <div className="col-span-2">
                                            <span className="text-muted-foreground">Ошибка:</span>{' '}
                                            <span className="text-destructive">{item.error_message}</span>
                                          </div>
                                        )}
                                      </div>
                                    </div>
                                  </div>

                                  <Button
                                    variant="outline"
                                    size="sm"
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      handleHistoryItemClick(event, item);
                                    }}
                                  >
                                    <Icon name="Eye" size={14} className="mr-1" />
                                    Детали
                                  </Button>
                                </div>
                              </div>
                            ))}
                        </div>
                      </TableCell>
                    </TableRow>
                  )}
                </React.Fragment>
              );
            })
          )}
        </TableBody>
      </Table>
    </div>
    </>
  );
};

export default EventsTable;