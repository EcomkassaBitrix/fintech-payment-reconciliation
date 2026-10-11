import { useCallback, useEffect, useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import Icon from '@/components/ui/icon';
import { useToast } from '@/hooks/use-toast';
import { useAuth } from '@/contexts/AuthContext';
import { formatDateTime } from '@/lib/formatDate';
import functionUrls from '../../../backend/func2url.json';
import PlatformAdminsCard from './PlatformAdminsCard';
import MaintenanceCard from './MaintenanceCard';
import CronSourcesList, { CronSource } from './CronSourcesList';

const api = (functionUrls as Record<string, string>)['platform-settings'];

interface PlatformSettings {
  managing_company_id: number | null;
  cron_enabled: boolean;
  cron_token: string;
  cron_last_tick_at: string | null;
  cron_last_result: { companies: number; failed: number } | null;
  metrika_counter_id: string | null;
  cron_sources: Record<string, boolean>;
  maintenance_enabled: boolean;
  maintenance_message: string | null;
  maintenance_until: string | null;
  messenger_api_url: string | null;
  messenger_api_url_default: string;
}

interface CompanyOption {
  id: number;
  name: string;
  inn: string | null;
}

const AdminSettingsSection = () => {
  const { user } = useAuth();
  const { toast } = useToast();
  const [settings, setSettings] = useState<PlatformSettings | null>(null);
  const [companies, setCompanies] = useState<CompanyOption[]>([]);
  const [problems, setProblems] = useState<string[]>([]);
  const [interval, setIntervalMin] = useState(1);
  const [managingId, setManagingId] = useState<string>('');
  const [cronEnabled, setCronEnabled] = useState(false);
  const [metrikaId, setMetrikaId] = useState('');
  const [messengerUrl, setMessengerUrl] = useState('');
  const [sources, setSources] = useState<CronSource[]>([]);
  const [sourceValues, setSourceValues] = useState<Record<string, boolean>>({});
  const [sourceIntervals, setSourceIntervals] = useState<Record<string, string>>({});
  const [isSaving, setIsSaving] = useState(false);
  const [isSavingMessenger, setIsSavingMessenger] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const apply = (data: { settings: PlatformSettings; companies: CompanyOption[]; cron_problems: string[]; cron_interval_min: number; cron_sources?: CronSource[] }) => {
    setSettings(data.settings);
    setCompanies(data.companies || []);
    setProblems(data.cron_problems || []);
    setIntervalMin(data.cron_interval_min || 1);
    setManagingId(data.settings.managing_company_id ? String(data.settings.managing_company_id) : '');
    setCronEnabled(data.settings.cron_enabled);
    setMetrikaId(data.settings.metrika_counter_id || '');
    setMessengerUrl(data.settings.messenger_api_url || '');
    const list = data.cron_sources || [];
    setSources(list);
    setSourceValues(Object.fromEntries(list.map((s) => [s.key, s.enabled])));
    setSourceIntervals(Object.fromEntries(list.map((s) => [s.key, s.interval])));
  };

  const load = useCallback(async () => {
    if (!user) return;
    const res = await fetch(`${api}?requester_user_id=${user.user_id}`);
    const data = await res.json();
    if (res.ok) apply(data);
    else setError(data.error || 'Не удалось загрузить настройки');
  }, [user]);

  useEffect(() => {
    load();
  }, [load]);

  const save = async () => {
    if (!user) return;
    setIsSaving(true);
    try {
      const res = await fetch(api, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action: 'save',
          requester_user_id: user.user_id,
          managing_company_id: managingId ? Number(managingId) : null,
          cron_enabled: cronEnabled,
          metrika_counter_id: metrikaId || null,
          cron_sources: sourceValues,
          cron_intervals: sourceIntervals
        })
      });
      const data = await res.json();
      if (res.ok) {
        apply(data);
        toast({
          title: 'Настройки сохранены',
          description: 'Кабинеты клиентов применят режим запуска после обновления страницы'
        });
      } else {
        toast({ title: 'Ошибка', description: data.error, variant: 'destructive' });
      }
    } finally {
      setIsSaving(false);
    }
  };

  const saveMessenger = async () => {
    if (!user || !settings) return;
    setIsSavingMessenger(true);
    try {
      const res = await fetch(api, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'save_messenger', requester_user_id: user.user_id, messenger_api_url: messengerUrl.trim() || null })
      });
      const data = await res.json();
      if (res.ok) {
        setSettings({ ...settings, messenger_api_url: data.messenger_api_url });
        setMessengerUrl(data.messenger_api_url || '');
        toast({ title: 'Адрес сохранён', description: data.messenger_api_url ? 'Сообщения и письма уходят через новый адрес' : 'Используется адрес по умолчанию' });
      } else {
        toast({ title: 'Ошибка', description: data.error, variant: 'destructive' });
      }
    } finally {
      setIsSavingMessenger(false);
    }
  };

  const copy = (text: string) => {
    navigator.clipboard.writeText(text).then(() => toast({ title: 'Скопировано' }));
  };

  if (error) {
    return <div className="text-destructive">{error}</div>;
  }
  if (!settings) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Icon name="Loader2" size={28} className="animate-spin text-muted-foreground" />
      </div>
    );
  }

  const hasChanges = (managingId || '') !== (settings.managing_company_id ? String(settings.managing_company_id) : '')
    || cronEnabled !== settings.cron_enabled
    || metrikaId !== (settings.metrika_counter_id || '')
    || sources.some((s) => sourceValues[s.key] !== s.enabled || sourceIntervals[s.key] !== s.interval);
  const tickCommand = `curl -s -X POST ${api} -H 'Content-Type: application/json' -H 'X-Cron-Token: ${settings.cron_token}' -d '{"action":"tick"}'`;

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h2 className="text-3xl font-display font-bold text-foreground mb-2">Настройки</h2>
        <p className="text-muted-foreground">Параметры всей платформы</p>
      </div>

      <MaintenanceCard
        enabled={settings.maintenance_enabled}
        message={settings.maintenance_message}
        until={settings.maintenance_until}
        onSaved={load}
      />

      <Card className="border-border bg-card">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Icon name="Landmark" size={20} />
            Управляющая компания
          </CardTitle>
          <CardDescription>
            От её имени принимаются оплаты подписок клиентов и выставляются документы
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="max-w-md">
            <Select value={managingId} onValueChange={setManagingId}>
              <SelectTrigger>
                <SelectValue placeholder="Выберите компанию" />
              </SelectTrigger>
              <SelectContent>
                {companies.map((c) => (
                  <SelectItem key={c.id} value={String(c.id)}>
                    {c.name}{c.inn ? ` · ИНН ${c.inn}` : ''}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      <Card className="border-border bg-card">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Icon name="BarChart3" size={20} />
            Яндекс Метрика
          </CardTitle>
          <CardDescription>
            Номер счётчика из кабинета Метрики — сайт подключит его на всех страницах. Пусто — счётчик выключен.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          <Input
            value={metrikaId}
            onChange={(e) => setMetrikaId(e.target.value.replace(/\D/g, '').slice(0, 20))}
            placeholder="Например, 12345678"
            inputMode="numeric"
            className="max-w-xs font-mono"
          />
          <p className="text-xs text-muted-foreground">
            Номер — цифры в названии счётчика на metrika.yandex.ru. Применится у посетителей после обновления страницы.
          </p>
        </CardContent>
      </Card>

      <Card className="border-border bg-card">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Icon name="Send" size={20} />
            Сервис отправки сообщений и писем
          </CardTitle>
          <CardDescription>
            Через этот адрес уходят коды входа, приглашения и уведомления в Telegram, WhatsApp, Max и на почту
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          <div className="flex flex-col gap-2 sm:flex-row">
            <Input
              value={messengerUrl}
              onChange={(e) => setMessengerUrl(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') saveMessenger(); }}
              placeholder={settings.messenger_api_url_default}
              className="font-mono"
            />
            <Button
              onClick={saveMessenger}
              disabled={isSavingMessenger || messengerUrl.trim() === (settings.messenger_api_url || '')}
              className="gap-2 shrink-0"
            >
              <Icon name={isSavingMessenger ? 'Loader2' : 'Save'} size={16} className={isSavingMessenger ? 'animate-spin' : ''} />
              Сохранить
            </Button>
          </div>
          <p className="text-xs text-muted-foreground">
            Пусто — используется адрес по умолчанию: <span className="font-mono break-all">{settings.messenger_api_url_default}</span>.
            Новый адрес применяется сразу после сохранения. Ключ доступа к сервису (MESSENGER_API_KEY) остаётся прежним.
          </p>
        </CardContent>
      </Card>

      <Card className="border-border bg-card">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Icon name="Timer" size={20} />
            Фоновые задачи
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
                открытии страниц и ручных действиях, как сейчас.
              </span>
            </span>
          </label>

          {settings.cron_enabled ? (
            <div className="space-y-3 rounded-lg border border-border p-4">
              <div className="text-sm font-medium">Задание для планировщика (раз в {interval} мин)</div>
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
                {settings.cron_last_tick_at ? (
                  <>
                    {formatDateTime(settings.cron_last_tick_at, undefined, true)}
                    {settings.cron_last_result && (
                      <span className="text-muted-foreground">
                        {' '}· компаний: {settings.cron_last_result.companies}
                        {settings.cron_last_result.failed > 0 && `, с ошибками: ${settings.cron_last_result.failed}`}
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

          {sources.length > 0 && (
            <CronSourcesList
              sources={sources}
              values={sourceValues}
              intervals={sourceIntervals}
              onChange={(key, enabled) => setSourceValues((prev) => ({ ...prev, [key]: enabled }))}
              onIntervalChange={(key, value) => setSourceIntervals((prev) => ({ ...prev, [key]: value }))}
            />
          )}

          {problems.map((p) => (
            <div key={p} className="flex items-start gap-2 rounded-lg border border-warning/40 bg-warning/10 p-3 text-sm text-foreground">
              <Icon name="AlertTriangle" size={16} className="mt-0.5 shrink-0 text-warning" />
              <span>{p}</span>
            </div>
          ))}
        </CardContent>
      </Card>

      <Button onClick={save} disabled={!hasChanges || isSaving}>
        {isSaving ? 'Сохранение...' : 'Сохранить'}
      </Button>

      <PlatformAdminsCard />
    </div>
  );
};

export default AdminSettingsSection;
