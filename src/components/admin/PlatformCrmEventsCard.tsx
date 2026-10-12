import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import Icon from '@/components/ui/icon';
import { formatDateTime } from '@/lib/formatDate';
import { CRM_EVENT_KINDS, CRM_EVENT_STATUSES, PlatformCrmEvent, describeResult } from './platformCrmTypes';

interface Props {
  events: PlatformCrmEvent[];
  pending: number;
  busy: boolean;
  onRetry: (eventId?: number) => void;
}

const PlatformCrmEventsCard = ({ events, pending, busy, onRetry }: Props) => (
  <Card className="border-border bg-card">
    <CardHeader className="flex flex-row items-start justify-between gap-4 space-y-0">
      <div>
        <CardTitle className="text-lg">Журнал передачи</CardTitle>
        <CardDescription>
          Последние 30 событий{pending > 0 ? ` · в очереди ${pending}` : ''}. Ошибки повторяются сами через 1, 5, 15 и 60 минут
        </CardDescription>
      </div>
      <Button variant="outline" size="sm" disabled={busy} onClick={() => onRetry()}>
        <Icon name={busy ? 'Loader2' : 'Play'} size={14} className={`mr-2 ${busy ? 'animate-spin' : ''}`} />
        Отправить очередь
      </Button>
    </CardHeader>
    <CardContent>
      {events.length === 0 ? (
        <p className="text-sm text-muted-foreground py-6 text-center">
          Событий пока нет — они появятся после первой регистрации при включённой передаче
        </p>
      ) : (
        <div className="divide-y divide-border">
          {events.map((e) => {
            const st = CRM_EVENT_STATUSES[e.status] || CRM_EVENT_STATUSES.new;
            const result = describeResult(e);
            return (
              <div key={e.id} className="py-3 flex flex-col gap-1 sm:flex-row sm:items-start sm:justify-between">
                <div className="min-w-0 space-y-0.5">
                  <div className="flex items-center gap-2 flex-wrap text-sm">
                    <span className="font-medium text-foreground">{CRM_EVENT_KINDS[e.kind] || e.kind}</span>
                    <Badge variant="outline" className={st.className}>{st.label}</Badge>
                    <span className="text-muted-foreground">{formatDateTime(e.created_at)}</span>
                  </div>
                  <p className="text-sm text-muted-foreground">
                    {[e.full_name, e.phone ? `+${e.phone}` : null,
                      e.company_name ? `${e.company_name}${e.company_inn ? `, ИНН ${e.company_inn}` : ''}` : null]
                      .filter(Boolean).join(' · ') || '—'}
                  </p>
                  {result && <p className="text-xs text-success">{result}</p>}
                  {e.error && e.status !== 'done' && <p className="text-xs text-destructive break-words">{e.error}</p>}
                </div>
                {(e.status === 'failed' || e.status === 'retry') && (
                  <Button variant="ghost" size="sm" disabled={busy} onClick={() => onRetry(e.id)} className="shrink-0">
                    <Icon name="RotateCcw" size={14} className="mr-1" />
                    Повторить
                  </Button>
                )}
              </div>
            );
          })}
        </div>
      )}
    </CardContent>
  </Card>
);

export default PlatformCrmEventsCard;
