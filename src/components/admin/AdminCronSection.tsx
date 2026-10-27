import { useCallback, useEffect, useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import Icon from '@/components/ui/icon';
import { useToast } from '@/hooks/use-toast';
import { useAuth } from '@/contexts/AuthContext';
import { formatDateTime } from '@/lib/formatDate';
import functionUrls from '../../../backend/func2url.json';
import CronSourcesList, { CronSource } from './CronSourcesList';
import AutomationQueueStats, { AutomationQueue } from './AutomationQueueStats';

const api = (functionUrls as Record<string, string>)['platform-settings'];

interface CronData {
  cron_enabled: boolean;
  cron_token: string;
  cron_last_tick_at: string | null;
  cron_last_result: { companies: number; failed: number } | null;
  cron_interval_min: number;
  cron_problems: string[];
  cron_sources: CronSource[];
  automation_queue: AutomationQueue | null;
}

const AdminCronSection = () => {
  const { user } = useAuth();
  const { toast } = useToast();
  const [data, setData] = useState<CronData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cronEnabled, setCronEnabled] = useState(false);
  const [sourceValues, setSourceValues] = useState<Record<string, boolean>>({});
  const [sourceIntervals, setSourceIntervals] = useState<Record<string, string>>({});
  const [isSaving, setIsSaving] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [running, setRunning] = useState<string | null>(null);

  const apply = (d: CronData, resetForm: boolean) => {
    setData(d);
    if (resetForm) {
      setCronEnabled(d.cron_enabled);
      setSourceValues(Object.fromEntries(d.cron_sources.map((s) => [s.key, s.enabled])));
      setSourceIntervals(Object.fromEntries(d.cron_sources.map((s) => [s.key, s.interval])));
    }
  };

  const load = useCallback(async (resetForm = true) => {
    if (!user) return;
    const res = await fetch(`${api}?requester_user_id=${user.user_id}&section=cron`);
    const d = await res.json();
    if (res.ok) apply(d, resetForm);
    else setError(d.error || 'Не удалось загрузить фоновые задачи');
  }, [user]);

  useEffect(() => {
    load();
  }, [load]);

  const refresh = async () => {
    setRefreshing(true);
    try {
      await load(false);
    } finally {
      setRefreshing(false);
    }
  };

  const save = async () => {
    if (!user) return;
    setIsSaving(true);
    try {
      const res = await fetch(api, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action: 'save_cron',
          requester_user_id: user.user_id,
          cron_enabled: cronEnabled,
          cron_sources: sourceValues,
          cron_intervals: sourceIntervals
        })
      });
      const d = await res.json();
      if (res.ok) {
        apply(d, true);
        toast({ title: 'Настройки сохранены', description: 'Планировщик применит их при следующем запуске' });
      } else {
        toast({ title: 'Ошибка', description: d.error, variant: 'destructive' });
      }
    } finally {
      setIsSaving(false);
    }
  };

  const runNow = async (source: string) => {
    if (!user) return;
    setRunning(source);
    try {
      const res = await fetch(api, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'run_now', requester_user_id: user.user_id, source })
      });
      const d = await res.json();
      if (!res.ok) {
        toast({ title: 'Ошибка', description: d.error, variant: 'destructive' });
        return;
      }
      apply(d, false);
      if (!d.started) {
        toast({ title: 'Нечего загружать', description: 'Ни у одной компании нет подключения для этой задачи' });
      } else if (d.errors?.length) {
        toast({ title: 'Запущено с ошибками', description: d.errors.join('; '), variant: 'destructive' });
      } else {
        toast({ title: 'Загрузка запущена', description: 'Итог появится в списке через минуту — нажмите «Обновить»' });
        setTimeout(() => load(false), 20000);
      }
    } finally {
      setRunning(null);
    }
  };

  const copy = (text: string) => {
    navigator.clipboard.writeText(text).then(() => toast({ title: 'Скопировано' }));
  };

  if (error) return <div className="text-destructive">{error}</div>;
  if (!data) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Icon name="Loader2" size={28} className="animate-spin text-muted-foreground" />
      </div>
    );
  }

  const hasChanges = cronEnabled !== data.cron_enabled
    || data.cron_sources.some((s) => sourceValues[s.key] !== s.enabled || sourceIntervals[s.key] !== s.interval);
  const tickCommand = `curl -s -X POST ${api} -H 'Content-Type: application/json' -H 'X-Cron-Token: ${data.cron_token}' -d '{"action":"tick"}'`;

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-3xl font-display font-bold text-foreground mb-2">Фоновые задачи</h2>
          <p className="text-muted-foreground">
            Загрузка чеков, выписок и документов кассы, очередь автоматизации и автосписания подписок
          </p>
        </div>
        <Button variant="outline" onClick={refresh} disabled={refreshing} className="gap-2 shrink-0">
          <Icon name="RefreshCw" size={16} className={refreshing ? 'animate-spin' : ''} />
          Обновить
        </Button>
      </div>

      {data.cron_problems.map((p) => (
        <div key={p} className="flex items-start gap-2 rounded-lg border border-warning/40 bg-warning/10 p-3 text-sm text-foreground">
          <Icon name="AlertTriangle" size={16} className="mt-0.5 shrink-0 text-warning" />
          <span>{p}</span>
        </div>
      ))}

      <Card className="border-border bg-card">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Icon name="Timer" size={20} />
            Планировщик
          </CardTitle>
          <CardDescription>
            Очередь автоматизации, повторы сценариев, рассылка уведомлений, проверка «платежи без чека», дозагрузка чеков кассы
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <label className="flex items-start gap-3">
            <Checkbox checked={cronEnabled} onCheckedChange={(v) => setCronEnabled(Boolean(v))} className="mt-0.5" />
            <span>
              <span className="text-sm font-medium">Активировать работу по cron</span>
              <span className="block text-xs text-muted-foreground">
                Для всех клиентов: задачи запускает планировщик сервера по расписанию. Выключено — запуск при входе в кабинет,
                открытии страниц и ручных действиях.
              </span>
            </span>
          </label>

          {data.cron_enabled ? (
            <div className="space-y-3 rounded-lg border border-border p-4">
              <div className="text-sm font-medium">Задание для планировщика (раз в {data.cron_interval_min} мин)</div>
              <div className="flex items-start gap-2">
                <code className="flex-1 break-all rounded bg-muted p-2 text-xs">{tickCommand}</code>
                <Button size="icon" variant="ghost" onClick={() => copy(tickCommand)} title="Скопировать">
                  <Icon name="Copy" size={16} />
                </Button>
              </div>
              <p className="text-xs text-muted-foreground">
                Для crontab: <code className="rounded bg-muted px-1">* * * * * {'<команда выше>'}</code>
              </p>
              <div className="text-sm">
                Последний запуск:{' '}
                {data.cron_last_tick_at ? (
                  <>
                    {formatDateTime(data.cron_last_tick_at, undefined, true)}
                    {data.cron_last_result && (
                      <span className="text-muted-foreground">
                        {' '}· компаний: {data.cron_last_result.companies}
                        {data.cron_last_result.failed > 0 && `, с ошибками: ${data.cron_last_result.failed}`}
                      </span>
                    )}
                  </>
                ) : (
                  <span className="text-muted-foreground">ещё не было</span>
                )}
              </div>
            </div>
          ) : (
            <div className="flex items-start gap-2 rounded-lg bg-muted/50 p-3 text-xs text-muted-foreground">
              <Icon name="Info" size={14} className="mt-0.5 shrink-0" />
              <span>Сейчас задачи запускаются из открытых кабинетов клиентов. Если кабинет никто не открывает, задачи ждут ближайшего входа.</span>
            </div>
          )}

          {data.automation_queue && (
            <AutomationQueueStats queue={data.automation_queue} onRefresh={refresh} refreshing={refreshing} />
          )}

          {data.cron_sources.length > 0 && (
            <CronSourcesList
              sources={data.cron_sources}
              values={sourceValues}
              intervals={sourceIntervals}
              onChange={(key, enabled) => setSourceValues((prev) => ({ ...prev, [key]: enabled }))}
              onIntervalChange={(key, value) => setSourceIntervals((prev) => ({ ...prev, [key]: value }))}
              onRunNow={runNow}
              running={running}
            />
          )}

          <Button onClick={save} disabled={!hasChanges || isSaving} className="gap-2">
            <Icon name={isSaving ? 'Loader2' : 'Save'} size={16} className={isSaving ? 'animate-spin' : ''} />
            Сохранить
          </Button>
        </CardContent>
      </Card>
    </div>
  );
};

export default AdminCronSection;
