import { useEffect, useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import Icon from '@/components/ui/icon';
import { useToast } from '@/hooks/use-toast';
import { formatDateTime } from '@/lib/formatDate';
import functionUrls from '../../../backend/func2url.json';

interface LogItem {
  action: string;
  details: string | null;
  created_at: string;
  user_name: string | null;
}

interface AccessState {
  enabled: boolean;
  until: string | null;
  granted_by: string | null;
  log: LogItem[];
}

const DURATIONS = [
  { value: '1d', label: '1 день' },
  { value: '7d', label: '7 дней' },
  { value: '30d', label: '30 дней' },
  { value: 'forever', label: 'Бессрочно' }
];

const LOG_LABELS: Record<string, string> = {
  grant: 'Доступ открыт',
  revoke: 'Доступ закрыт',
  enter: 'Поддержка вошла в кабинет',
  change: 'Поддержка изменила настройки'
};

const api = (functionUrls as Record<string, string>)['company-settings-update'];

const SupportAccessCard = ({ companyId, timezone }: { companyId: number; timezone?: string }) => {
  const { toast } = useToast();
  const [state, setState] = useState<AccessState | null>(null);
  const [duration, setDuration] = useState('7d');
  const [busy, setBusy] = useState(false);
  const [showLog, setShowLog] = useState(false);

  useEffect(() => {
    fetch(`${api}?company_id=${companyId}`)
      .then((r) => r.json())
      .then((d) => d.success && setState(d))
      .catch(() => undefined);
  }, [companyId]);

  const change = async (action: 'grant' | 'revoke') => {
    setBusy(true);
    try {
      const res = await fetch(api, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action, company_id: companyId, duration })
      });
      const data = await res.json();
      if (res.ok && data.success) {
        setState(data);
        toast({ title: action === 'grant' ? 'Доступ поддержке открыт' : 'Доступ поддержке закрыт' });
      } else {
        toast({ title: 'Ошибка', description: data.error, variant: 'destructive' });
      }
    } catch {
      toast({ title: 'Ошибка подключения', variant: 'destructive' });
    } finally {
      setBusy(false);
    }
  };

  if (!state) return null;

  return (
    <Card className="border-border bg-card">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Icon name="LifeBuoy" size={20} />
          Доступ поддержки
        </CardTitle>
        <CardDescription>
          Разрешите специалисту Сверки зайти в ваш кабинет и настроить интеграции, сценарии и чеки за вас.
          Доступ закроется сам по окончании срока, выключить его можно в любой момент.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center justify-between gap-4 rounded-lg border border-border p-4">
          <div>
            <p className="font-medium text-foreground">
              {state.enabled ? 'Доступ открыт' : 'Доступ закрыт'}
            </p>
            <p className="text-sm text-muted-foreground">
              {state.enabled
                ? state.until
                  ? `До ${formatDateTime(state.until, timezone)}`
                  : 'Бессрочно, пока вы не выключите'
                : 'Поддержка не видит ваш кабинет'}
            </p>
          </div>
          <Switch
            checked={state.enabled}
            disabled={busy}
            onCheckedChange={(v) => change(v ? 'grant' : 'revoke')}
          />
        </div>

        {!state.enabled && (
          <div className="flex items-center gap-3">
            <span className="text-sm text-muted-foreground">Срок доступа</span>
            <Select value={duration} onValueChange={setDuration}>
              <SelectTrigger className="w-40">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {DURATIONS.map((d) => (
                  <SelectItem key={d.value} value={d.value}>{d.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}

        {state.enabled && (
          <Button variant="outline" size="sm" disabled={busy} onClick={() => change('grant')}>
            <Icon name="RefreshCw" size={14} className="mr-2" />
            Продлить на
            <span className="ml-1">{DURATIONS.find((d) => d.value === duration)?.label.toLowerCase()}</span>
          </Button>
        )}

        {state.log.length > 0 && (
          <div>
            <button
              type="button"
              className="text-sm text-primary hover:underline"
              onClick={() => setShowLog(!showLog)}
            >
              {showLog ? 'Скрыть журнал' : 'Журнал действий поддержки'}
            </button>
            {showLog && (
              <ul className="mt-3 space-y-2">
                {state.log.map((l, i) => (
                  <li key={i} className="flex justify-between gap-4 text-sm border-b border-border pb-2">
                    <span className="text-foreground">
                      {LOG_LABELS[l.action] || l.action}
                      {l.action === 'grant' && l.details ? ` (${l.details.replace('Доступ открыт ', '')})` : ''}
                      {l.user_name && <span className="text-muted-foreground"> · {l.user_name}</span>}
                    </span>
                    <span className="text-muted-foreground shrink-0">{formatDateTime(l.created_at, timezone)}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
};

export default SupportAccessCard;
