import { useEffect, useState } from 'react';
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
  const [open, setOpen] = useState(false);

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

  const statusText = state.enabled
    ? state.until
      ? `Доступ открыт до ${formatDateTime(state.until, timezone)}`
      : 'Доступ открыт бессрочно'
    : 'Поддержка не видит ваш кабинет';

  return (
    <div className={`rounded-lg border bg-card ${state.enabled ? 'border-primary/40' : 'border-border'}`}>
      <div className="flex items-center gap-3 px-4 py-3">
        <button type="button" onClick={() => setOpen(!open)} className="flex min-w-0 flex-1 items-center gap-3 text-left">
          <Icon name={open ? 'ChevronDown' : 'ChevronRight'} size={18} className="shrink-0 text-muted-foreground" />
          <div className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg ${state.enabled ? 'bg-primary/10' : 'bg-muted'}`}>
            <Icon name="LifeBuoy" size={18} className={state.enabled ? 'text-primary' : 'text-muted-foreground'} />
          </div>
          <div className="min-w-0">
            <div className="font-medium text-foreground">Поддержка Сверки</div>
            <div className={`truncate text-sm ${state.enabled ? 'text-primary' : 'text-muted-foreground'}`}>{statusText}</div>
          </div>
        </button>
        <Switch
          checked={state.enabled}
          disabled={busy}
          onCheckedChange={(v) => change(v ? 'grant' : 'revoke')}
        />
      </div>

      {open && (
        <div className="space-y-4 border-t border-border px-4 py-4">
          <p className="text-sm text-muted-foreground">
            Разрешите специалисту Сверки зайти в ваш кабинет и настроить интеграции, сценарии и чеки за вас.
            Доступ закроется сам по окончании срока, выключить его можно в любой момент.
          </p>

          <div className="flex flex-wrap items-center gap-3">
            <span className="text-sm text-muted-foreground">{state.enabled ? 'Продлить на' : 'Срок доступа'}</span>
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
            {state.enabled && (
              <Button variant="outline" size="sm" disabled={busy} onClick={() => change('grant')}>
                <Icon name="RefreshCw" size={14} className="mr-2" />
                Продлить
              </Button>
            )}
          </div>

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
                    <li key={i} className="flex justify-between gap-4 border-b border-border pb-2 text-sm">
                      <span className="text-foreground">
                        {LOG_LABELS[l.action] || l.action}
                        {l.action === 'grant' && l.details ? ` (${l.details.replace('Доступ открыт ', '')})` : ''}
                        {l.user_name && <span className="text-muted-foreground"> · {l.user_name}</span>}
                      </span>
                      <span className="shrink-0 text-muted-foreground">{formatDateTime(l.created_at, timezone)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default SupportAccessCard;
