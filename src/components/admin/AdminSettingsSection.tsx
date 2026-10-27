import { useCallback, useEffect, useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import Icon from '@/components/ui/icon';
import { useToast } from '@/hooks/use-toast';
import { useAuth } from '@/contexts/AuthContext';
import functionUrls from '../../../backend/func2url.json';
import PlatformAdminsCard from './PlatformAdminsCard';

const api = (functionUrls as Record<string, string>)['platform-settings'];

interface PlatformSettings {
  managing_company_id: number | null;
  cron_enabled: boolean;
  cron_token: string;
  cron_last_tick_at: string | null;
  cron_last_result: { companies: number; failed: number } | null;
  metrika_counter_id: string | null;
  metrika_script: string | null;
  cron_sources: Record<string, boolean>;
  maintenance_enabled: boolean;
  maintenance_message: string | null;
  maintenance_until: string | null;
  messenger_api_url: string | null;
  messenger_api_url_default: string;
  contact_email: string | null;
  contact_phone: string | null;
  contact_email_default: string | null;
  contact_phone_default: string | null;
  contact_address: string | null;
  contact_address_default: string | null;
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
  const [managingId, setManagingId] = useState<string>('');
  const [metrikaId, setMetrikaId] = useState('');
  const [metrikaScript, setMetrikaScript] = useState('');
  const [contactEmail, setContactEmail] = useState('');
  const [contactPhone, setContactPhone] = useState('');
  const [contactAddress, setContactAddress] = useState('');
  const [messengerUrl, setMessengerUrl] = useState('');
  const [isSaving, setIsSaving] = useState(false);
  const [isSavingMessenger, setIsSavingMessenger] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const apply = (data: { settings: PlatformSettings; companies: CompanyOption[] }) => {
    setSettings(data.settings);
    setCompanies(data.companies || []);
    setManagingId(data.settings.managing_company_id ? String(data.settings.managing_company_id) : '');
    setMetrikaId(data.settings.metrika_counter_id || '');
    setMetrikaScript(data.settings.metrika_script || '');
    setContactEmail(data.settings.contact_email || '');
    setContactPhone(data.settings.contact_phone || '');
    setContactAddress(data.settings.contact_address || '');
    setMessengerUrl(data.settings.messenger_api_url || '');
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
          metrika_counter_id: metrikaId || null,
          metrika_script: metrikaScript.trim() || null,
          contact_email: contactEmail.trim() || null,
          contact_phone: contactPhone.trim() || null,
          contact_address: contactAddress.trim() || null
        })
      });
      const data = await res.json();
      if (res.ok) {
        apply(data);
        toast({
          title: 'Настройки сохранены',
          description: 'Изменения применены'
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

  const companyChanges = (managingId || '') !== (settings.managing_company_id ? String(settings.managing_company_id) : '')
    || contactEmail.trim() !== (settings.contact_email || '')
    || contactPhone.trim() !== (settings.contact_phone || '')
    || contactAddress.trim() !== (settings.contact_address || '');
  const hasChanges = companyChanges
    || metrikaId !== (settings.metrika_counter_id || '')
    || metrikaScript.trim() !== (settings.metrika_script || '');

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h2 className="text-3xl font-display font-bold text-foreground mb-2">Настройки</h2>
        <p className="text-muted-foreground">Параметры всей платформы</p>
      </div>

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
        <CardContent className="space-y-4">
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
          <div className="grid max-w-2xl gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label>Почта для клиентов</Label>
              <Input
                type="email"
                value={contactEmail}
                onChange={(e) => setContactEmail(e.target.value)}
                placeholder={settings?.contact_email_default || 'support@s-verka.ru'}
              />
            </div>
            <div className="space-y-1.5">
              <Label>Телефон для клиентов</Label>
              <Input
                type="tel"
                value={contactPhone}
                onChange={(e) => setContactPhone(e.target.value)}
                placeholder={settings?.contact_phone_default || '+7 900 000-00-00'}
              />
            </div>
            <div className="space-y-1.5 sm:col-span-2">
              <Label>Адрес</Label>
              <Input
                value={contactAddress}
                onChange={(e) => setContactAddress(e.target.value)}
                placeholder={settings?.contact_address_default || '123456, г. Москва, ул. Примерная, д. 1'}
              />
            </div>
          </div>
          <p className="text-xs text-muted-foreground">
            Показываются в подвале сайта и подставляются в договор и политику. Пустое поле — берутся почта и телефон
            владельца и юридический адрес управляющей компании (подсказка в поле).
          </p>
          <Button onClick={save} disabled={!companyChanges || isSaving} className="gap-2">
            <Icon name={isSaving ? 'Loader2' : 'Save'} size={16} className={isSaving ? 'animate-spin' : ''} />
            Сохранить
          </Button>
        </CardContent>
      </Card>

      <Card className="border-border bg-card">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Icon name="BarChart3" size={20} />
            Яндекс Метрика
          </CardTitle>
          <CardDescription>
            Код счётчика целиком или только его номер — сайт подключит счётчик в начале каждой страницы. Оба поля пусты — счётчик выключен.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-1.5">
            <Label>Код счётчика</Label>
            <Textarea
              value={metrikaScript}
              onChange={(e) => setMetrikaScript(e.target.value)}
              placeholder={'<!-- Yandex.Metrika counter -->\n<script type="text/javascript">…</script>\n<!-- /Yandex.Metrika counter -->'}
              rows={10}
              spellCheck={false}
              className="font-mono text-xs"
            />
            <p className="text-xs text-muted-foreground">
              Скопируйте код из Метрики: «Настройки счётчика» → «Код счётчика». Он вставляется на сайт как есть, с Вебвизором
              и всеми выбранными там опциями, а номер ниже подставится из кода сам.
            </p>
          </div>
          <div className="space-y-1.5">
            <Label>Номер счётчика</Label>
            <Input
              value={metrikaId}
              onChange={(e) => setMetrikaId(e.target.value.replace(/\D/g, '').slice(0, 20))}
              placeholder="Например, 12345678"
              inputMode="numeric"
              disabled={!!metrikaScript.trim()}
              className="max-w-xs font-mono"
            />
            <p className="text-xs text-muted-foreground">
              Нужен, только если код выше не вставлен — тогда счётчик подключится со стандартными настройками.
              Изменения видны на опубликованном сайте сразу после сохранения.
            </p>
          </div>
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

      <Button onClick={save} disabled={!hasChanges || isSaving}>
        {isSaving ? 'Сохранение...' : 'Сохранить'}
      </Button>

      <PlatformAdminsCard />
    </div>
  );
};

export default AdminSettingsSection;