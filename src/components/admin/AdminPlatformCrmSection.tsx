import { useCallback, useEffect, useMemo, useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Checkbox } from '@/components/ui/checkbox';
import { Select, SelectContent, SelectGroup, SelectItem, SelectLabel, SelectTrigger, SelectValue } from '@/components/ui/select';
import Icon from '@/components/ui/icon';
import { useToast } from '@/hooks/use-toast';
import { useAuth } from '@/contexts/AuthContext';
import functionUrls from '../../../backend/func2url.json';
import PlatformCrmEventsCard from './PlatformCrmEventsCard';
import { CrmReference, PlatformCrmEvent, PlatformCrmSettings, fieldOptions } from './platformCrmTypes';

const api = (functionUrls as Record<string, string>)['platform-settings'];
const NONE = '__none__';

const EMPTY: PlatformCrmSettings = {
  webhook_url: '', is_enabled: false, entity: 'deal', stage_id: null, phone_field: 'contact.PHONE',
  phone_field_type: 'crm_multifield', phone_to_contact: true, channel_field: null, channel_field_type: null,
  inn_field: 'requisite', inn_field_type: null, title_template: 'Регистрация в Сверке: {name}'
};

const AdminPlatformCrmSection = () => {
  const { user } = useAuth();
  const { toast } = useToast();
  const [form, setForm] = useState<PlatformCrmSettings>(EMPTY);
  const [ref, setRef] = useState<CrmReference | null>(null);
  const [refError, setRefError] = useState('');
  const [events, setEvents] = useState<PlatformCrmEvent[]>([]);
  const [pending, setPending] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadingRef, setLoadingRef] = useState(false);
  const [saving, setSaving] = useState(false);
  const [busy, setBusy] = useState(false);

  const loadReference = useCallback(async (url: string) => {
    if (!user || !url.trim()) return;
    setLoadingRef(true);
    setRefError('');
    try {
      const res = await fetch(`${api}?requester_user_id=${user.user_id}&section=crm_reference&webhook_url=${encodeURIComponent(url.trim())}`);
      const data = await res.json();
      if (data.success) setRef(data);
      else { setRef(null); setRefError(data.error || 'Не удалось загрузить данные портала'); }
    } catch {
      setRefError('Проблема с подключением к серверу');
    } finally {
      setLoadingRef(false);
    }
  }, [user]);

  useEffect(() => {
    if (!user) return;
    fetch(`${api}?requester_user_id=${user.user_id}&section=crm`)
      .then((r) => r.json())
      .then((data) => {
        if (!data.success) return;
        setForm({ ...EMPTY, ...data.crm, webhook_url: data.crm.webhook_url || '' });
        setEvents(data.events || []);
        setPending(data.pending || 0);
        if (data.crm.webhook_url) loadReference(data.crm.webhook_url);
      })
      .finally(() => setLoading(false));
  }, [user, loadReference]);

  const set = (patch: Partial<PlatformCrmSettings>) => setForm((f) => ({ ...f, ...patch }));

  const stageGroups = useMemo(() => {
    const list = ref?.stages[form.entity] || [];
    const groups: { key: string; label: string; items: typeof list }[] = [];
    list.forEach((s) => {
      const key = s.group_id || 'lead';
      let g = groups.find((x) => x.key === key);
      if (!g) { g = { key, label: s.group || 'Статусы лидов', items: [] }; groups.push(g); }
      g.items.push(s);
    });
    return groups;
  }, [ref, form.entity]);

  const phoneOptions = useMemo(() => fieldOptions(ref, ['contact', form.entity],
    (f) => f.code === 'PHONE' || f.custom && ['string', 'crm_multifield'].includes(f.type)), [ref, form.entity]);
  const channelOptions = useMemo(() => fieldOptions(ref, ['contact', form.entity],
    (f) => f.custom && ['string', 'enumeration'].includes(f.type)), [ref, form.entity]);
  const innOptions = useMemo(() => fieldOptions(ref, ['company'], (f) => f.custom && f.type === 'string'), [ref]);

  const typeOf = (value: string | null) =>
    [...phoneOptions, ...channelOptions, ...innOptions].find((o) => o.value === value)?.type || null;

  const save = async () => {
    if (!user) return;
    setSaving(true);
    try {
      const res = await fetch(api, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action: 'save_crm', requester_user_id: user.user_id, ...form,
          phone_field_type: typeOf(form.phone_field) || (form.phone_field.endsWith('.PHONE') ? 'crm_multifield' : null),
          channel_field_type: typeOf(form.channel_field),
          inn_field_type: typeOf(form.inn_field)
        })
      });
      const data = await res.json();
      if (!res.ok || !data.success) {
        toast({ title: 'Не сохранено', description: data.error, variant: 'destructive' });
        return;
      }
      setEvents(data.events || []);
      setPending(data.pending || 0);
      toast({ title: 'Настройки CRM сохранены', description: data.processed?.done ? `Передано событий: ${data.processed.done}` : undefined });
    } catch {
      toast({ title: 'Ошибка подключения', variant: 'destructive' });
    } finally {
      setSaving(false);
    }
  };

  const retry = async (eventId?: number) => {
    if (!user) return;
    setBusy(true);
    try {
      const res = await fetch(api, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'crm_retry', requester_user_id: user.user_id, event_id: eventId })
      });
      const data = await res.json();
      if (data.success) {
        setEvents(data.events || []);
        setPending(data.pending || 0);
        toast({ title: `Передано: ${data.processed?.done || 0}, с ошибкой: ${data.processed?.failed || 0}` });
      }
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return <div className="flex items-center justify-center h-96"><Icon name="Loader2" className="animate-spin text-primary" size={32} /></div>;
  }

  const entityWord = form.entity === 'deal' ? 'сделку' : 'лид';

  return (
    <div className="animate-fade-in space-y-6">
      <div>
        <h2 className="text-3xl font-display font-bold text-foreground mb-2">Интеграции CRM</h2>
        <p className="text-muted-foreground">Передача регистраций клиентов Сверки в ваш Битрикс24</p>
      </div>

      <Card className="border-border bg-card">
        <CardHeader className="flex flex-row items-start justify-between gap-4 space-y-0">
          <div>
            <CardTitle className="text-lg">Битрикс24</CardTitle>
            <CardDescription>
              Регистрация → контакт и {entityWord} · ФИО и почта → обновление контакта · новая компания → компания с ИНН
            </CardDescription>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <span className="text-sm text-muted-foreground">Передавать</span>
            <Switch checked={form.is_enabled} onCheckedChange={(v) => set({ is_enabled: v })} />
          </div>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="space-y-1.5">
            <Label>Входящий вебхук Битрикс24</Label>
            <div className="flex gap-2">
              <Input value={form.webhook_url || ''} placeholder="https://ваш-портал.bitrix24.ru/rest/1/код/"
                onChange={(e) => set({ webhook_url: e.target.value.replace(/\s+/g, '') })} className="font-mono text-sm" />
              <Button variant="outline" disabled={loadingRef || !form.webhook_url} onClick={() => loadReference(form.webhook_url || '')}>
                <Icon name={loadingRef ? 'Loader2' : 'PlugZap'} size={14} className={`mr-2 ${loadingRef ? 'animate-spin' : ''}`} />
                Проверить
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">
              Битрикс24 → Разработчикам → Другое → Входящий вебхук. Права: <b>crm</b>
            </p>
            {refError && <p className="text-xs text-destructive">{refError}</p>}
            {ref && !refError && <p className="text-xs text-success">Портал подключён: загружены воронки и поля</p>}
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label>Что создавать</Label>
              <Select value={form.entity} onValueChange={(v) => set({ entity: v as 'deal' | 'lead', stage_id: null })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="deal">Сделку (с контактом)</SelectItem>
                  <SelectItem value="lead">Лид (с контактом)</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>{form.entity === 'deal' ? 'Воронка и этап' : 'Статус лида'}</Label>
              <Select value={form.stage_id || ''} onValueChange={(v) => set({ stage_id: v })} disabled={!ref}>
                <SelectTrigger><SelectValue placeholder={ref ? 'Выберите этап' : 'Сначала проверьте вебхук'} /></SelectTrigger>
                <SelectContent>
                  {stageGroups.map((g) => (
                    <SelectGroup key={g.key}>
                      <SelectLabel className="text-xs text-muted-foreground">{g.label}</SelectLabel>
                      {g.items.map((s) => <SelectItem key={s.value} value={s.value}>{s.label}</SelectItem>)}
                    </SelectGroup>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="space-y-1.5">
            <Label>Название {form.entity === 'deal' ? 'сделки' : 'лида'}</Label>
            <Input value={form.title_template} onChange={(e) => set({ title_template: e.target.value })} />
            <p className="text-xs text-muted-foreground">{'{name}'} — ФИО или телефон клиента, {'{phone}'} — телефон</p>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label>Куда записать номер телефона</Label>
              <Select value={form.phone_field} onValueChange={(v) => set({ phone_field: v })} disabled={!ref}>
                <SelectTrigger><SelectValue placeholder="Телефон контакта" /></SelectTrigger>
                <SelectContent>
                  {(phoneOptions.length ? phoneOptions : [{ value: 'contact.PHONE', label: 'Контакт · Телефон', type: 'crm_multifield' }])
                    .map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}
                </SelectContent>
              </Select>
              <label className="flex items-center gap-2 text-xs text-muted-foreground pt-1">
                <Checkbox checked={form.phone_to_contact} onCheckedChange={(v) => set({ phone_to_contact: !!v })} />
                Также в стандартный «Телефон» контакта — по нему ищем дубли
              </label>
            </div>
            <div className="space-y-1.5">
              <Label>Поле «Канал коммуникации»</Label>
              <Select value={form.channel_field || NONE} onValueChange={(v) => set({ channel_field: v === NONE ? null : v })} disabled={!ref}>
                <SelectTrigger><SelectValue placeholder="Не передавать" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value={NONE}>Не передавать</SelectItem>
                  {channelOptions.map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">Куда пришёл код при регистрации: Telegram, MAX, WhatsApp, SMS. Для списка — вариант с таким же названием</p>
            </div>
          </div>

          <div className="space-y-1.5 sm:max-w-[50%] sm:pr-2">
            <Label>ИНН компании</Label>
            <Select value={form.inn_field} onValueChange={(v) => set({ inn_field: v })} disabled={!ref}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="requisite">Реквизиты компании (стандарт Битрикс24)</SelectItem>
                {innOptions.map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>

          <div className="flex justify-end">
            <Button onClick={save} disabled={saving}>
              {saving && <Icon name="Loader2" size={14} className="animate-spin mr-2" />}
              Сохранить
            </Button>
          </div>
        </CardContent>
      </Card>

      <PlatformCrmEventsCard events={events} pending={pending} busy={busy} onRetry={retry} />
    </div>
  );
};

export default AdminPlatformCrmSection;
