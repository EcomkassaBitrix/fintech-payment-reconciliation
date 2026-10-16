import { useCallback, useEffect, useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import Icon from '@/components/ui/icon';
import { useToast } from '@/hooks/use-toast';
import { useAuth } from '@/contexts/AuthContext';
import functionUrls from '../../../backend/func2url.json';

const api = (functionUrls as Record<string, string>)['notifications'];

const CHANNELS: { value: string; label: string; icon: string }[] = [
  { value: 'max', label: 'Max', icon: 'MessageCircle' },
  { value: 'whatsapp', label: 'WhatsApp', icon: 'Phone' },
  { value: 'telegram', label: 'Telegram', icon: 'Send' },
  { value: 'email', label: 'Email', icon: 'Mail' }
];

interface CatalogItem {
  kind: string;
  label: string;
}

const formatPhone = (phone?: string | null) => {
  const d = (phone || '').replace(/\D/g, '');
  if (d.length !== 11) return phone || '—';
  return `+${d[0]} ${d.slice(1, 4)} ${d.slice(4, 7)}-${d.slice(7, 9)}-${d.slice(9)}`;
};

const NotificationPreferences = ({ embedded = false }: { embedded?: boolean }) => {
  const { currentCompany, user } = useAuth();
  const { toast } = useToast();
  const [catalog, setCatalog] = useState<CatalogItem[]>([]);
  const [channel, setChannel] = useState<string | null>(null);
  const [kinds, setKinds] = useState<string[]>([]);
  const [saved, setSaved] = useState<{ channel: string | null; kinds: string[] }>({ channel: null, kinds: [] });
  const [contacts, setContacts] = useState<{ phone: string | null; email: string | null }>({ phone: null, email: null });
  const [isSaving, setIsSaving] = useState(false);
  const [isTesting, setIsTesting] = useState(false);

  const companyId = currentCompany?.id;
  const userId = user?.user_id;

  const load = useCallback(async () => {
    if (!companyId || !userId) return;
    const res = await fetch(`${api}?company_id=${companyId}&user_id=${userId}&prefs=1`);
    const data = await res.json();
    if (!res.ok) return;
    setCatalog(data.catalog || []);
    setChannel(data.channel);
    setKinds(data.kinds || []);
    setSaved({ channel: data.channel, kinds: data.kinds || [] });
    setContacts({ phone: data.phone, email: data.email });
  }, [companyId, userId]);

  useEffect(() => {
    load();
  }, [load]);

  const post = async (body: object) => {
    const res = await fetch(api, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ company_id: companyId, user_id: userId, ...body })
    });
    const data = await res.json().catch(() => ({}));
    return { ok: res.ok, data };
  };

  const save = async () => {
    setIsSaving(true);
    try {
      const { ok, data } = await post({ action: 'save_prefs', channel, kinds });
      if (ok) {
        setSaved({ channel, kinds });
        toast({ title: 'Настройки уведомлений сохранены' });
      } else {
        toast({ title: 'Ошибка', description: data.error, variant: 'destructive' });
      }
    } finally {
      setIsSaving(false);
    }
  };

  const test = async () => {
    if (!channel) return;
    setIsTesting(true);
    try {
      const { ok, data } = await post({ action: 'test', channel });
      toast(ok
        ? { title: 'Тестовое сообщение отправлено' }
        : { title: 'Не отправлено', description: data.error, variant: 'destructive' });
    } finally {
      setIsTesting(false);
    }
  };

  const hasChanges = channel !== saved.channel;
  const recipient = channel === 'email' ? contacts.email : formatPhone(contacts.phone);
  const missingEmail = channel === 'email' && !contacts.email;

  return (
    <Card className={embedded ? 'border-0 bg-transparent shadow-none' : 'border-border bg-card'}>
      <CardHeader className={embedded ? 'hidden' : undefined}>
        <CardTitle className="flex items-center gap-2">
          <Icon name="BellRing" size={20} />
          Мои уведомления
        </CardTitle>
        <CardDescription>
          Все уведомления видны в колокольчике кабинета. Выберите канал — и все они будут дублироваться лично вам.
          Если канал не выбран, уведомления остаются только в колокольчике. Настройка у каждого сотрудника своя.
        </CardDescription>
      </CardHeader>
      <CardContent className={embedded ? 'space-y-6 p-0' : 'space-y-6'}>
        <div className="space-y-2">
          <div className="text-sm font-medium">Куда присылать</div>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant={channel === null ? 'default' : 'outline'} onClick={() => setChannel(null)}>
              Не дублировать
            </Button>
            {CHANNELS.map((c) => (
              <Button
                key={c.value}
                size="sm"
                variant={channel === c.value ? 'default' : 'outline'}
                className="gap-1.5"
                onClick={() => setChannel(c.value)}
              >
                <Icon name={c.icon} size={14} />
                {c.label}
              </Button>
            ))}
          </div>
          {channel && (
            <p className={`text-xs ${missingEmail ? 'text-destructive' : 'text-muted-foreground'}`}>
              {missingEmail
                ? 'В вашем профиле не указан email - сообщения не дойдут'
                : channel === 'email'
                  ? `На почту ${recipient}`
                  : `На номер входа в кабинет: ${recipient}`}
            </p>
          )}
        </div>

        <div className="space-y-2">
          <div className="text-sm font-medium">Что приходит</div>
          <ul className="space-y-1 text-sm text-muted-foreground">
            {catalog.map((item) => (
              <li key={item.kind} className="flex items-start gap-2">
                <Icon name="Check" size={14} className="mt-0.5 shrink-0 text-primary" />
                {item.label}
              </li>
            ))}
          </ul>
        </div>

        <div className="flex flex-wrap gap-2">
          <Button onClick={save} disabled={!hasChanges || isSaving}>
            {isSaving ? 'Сохранение...' : 'Сохранить'}
          </Button>
          <Button variant="outline" className="gap-1.5" onClick={test} disabled={!channel || missingEmail || isTesting}>
            <Icon name={isTesting ? 'Loader2' : 'Send'} size={14} className={isTesting ? 'animate-spin' : ''} />
            Отправить тест
          </Button>
        </div>
      </CardContent>
    </Card>
  );
};

export default NotificationPreferences;
