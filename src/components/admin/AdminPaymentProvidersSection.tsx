import { useEffect, useState } from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
import Icon from '@/components/ui/icon';
import { useToast } from '@/hooks/use-toast';
import { formatDateTime } from '@/lib/formatDate';
import functionUrls from '../../../backend/func2url.json';
import TbankTerminalForm, { TbankConfig } from './TbankTerminalForm';
import AdminSubscriptionTransactions from './AdminSubscriptionTransactions';
import TbankWebhookUrl from './TbankWebhookUrl';
import TbankTestPanel from './TbankTestPanel';

interface PaymentProvider {
  slug: string;
  name: string;
  description: string | null;
  auth_type: string;
  is_enabled: boolean;
  shop_id: string | null;
  is_test: boolean;
  connected_at: string | null;
  connected_by: string | null;
  connected: boolean;
  configured: boolean;
  config?: TbankConfig;
}

const api = `${(functionUrls as Record<string, string>)['tochka-oauth']}?provider=yookassa`;

const AdminPaymentProvidersSection = () => {
  const { toast } = useToast();
  const [providers, setProviders] = useState<PaymentProvider[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [busySlug, setBusySlug] = useState<string | null>(null);
  const [editing, setEditing] = useState<string | null>(null);

  const replace = (p: PaymentProvider) => setProviders((prev) => prev.map((x) => (x.slug === p.slug ? p : x)));

  useEffect(() => {
    fetch(`${api}&action=list`)
      .then((r) => r.json())
      .then((d) => setProviders(d.providers || []))
      .catch(() => undefined)
      .finally(() => setIsLoading(false));

    const params = new URLSearchParams(window.location.search);
    if (params.get('yookassa') === 'connected') {
      toast({ title: 'Магазин ЮKassa подключён' });
      window.history.replaceState(null, '', '/admin?section=payments');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const post = async (slug: string, body: Record<string, unknown>, success: string) => {
    setBusySlug(slug);
    try {
      const res = await fetch(api, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ slug, ...body })
      });
      const data = await res.json();
      if (data.success) {
        replace(data.provider);
        setEditing(null);
        toast({ title: success });
      } else {
        toast({ title: 'Ошибка', description: data.error, variant: 'destructive' });
      }
    } catch {
      toast({ title: 'Ошибка подключения', variant: 'destructive' });
    } finally {
      setBusySlug(null);
    }
  };

  const connect = async (slug: string) => {
    setBusySlug(slug);
    try {
      const res = await fetch(`${api}&action=authorize_url`);
      const data = await res.json();
      if (data.success && data.authorize_url) {
        window.location.href = data.authorize_url;
        return;
      }
      toast({ title: 'Не удалось подключить', description: data.error, variant: 'destructive' });
    } catch {
      toast({ title: 'Ошибка подключения', variant: 'destructive' });
    }
    setBusySlug(null);
  };

  const check = async (slug: string) => {
    setBusySlug(slug);
    try {
      const res = await fetch(`${api}&action=check&slug=${slug}`);
      const data = await res.json();
      if (data.success) {
        const s = data.shop || {};
        toast({
          title: slug === 'tbank' ? 'Терминал отвечает' : 'Магазин отвечает',
          description: `№ ${s.account_id || '—'} · ${s.test ? 'тестовый' : 'боевой'} · статус ${s.status || '—'}`
        });
      } else {
        toast({ title: 'Проверка не прошла', description: data.error, variant: 'destructive' });
      }
    } finally {
      setBusySlug(null);
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-96">
        <Icon name="Loader2" className="animate-spin text-primary" size={32} />
      </div>
    );
  }

  return (
    <div className="animate-fade-in">
      <div className="mb-8">
        <h2 className="text-3xl font-display font-bold text-foreground mb-2">Оплата</h2>
        <p className="text-muted-foreground">
          Платёжные системы, через которые клиенты платят за подписку Сверки
        </p>
      </div>

      <div className="space-y-4">
        {providers.map((p) => {
          const busy = busySlug === p.slug;
          const isTbank = p.slug === 'tbank';
          const showForm = isTbank && (editing === p.slug || !p.connected);
          return (
            <Card key={p.slug} className="border-border bg-card">
              <CardContent className="p-5 space-y-4">
                <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                  <div className="flex items-start gap-3">
                    <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
                      <Icon name="Wallet" size={20} className="text-primary" />
                    </div>
                    <div>
                      <div className="flex items-center gap-2 flex-wrap">
                        <p className="font-medium text-foreground">{p.name}</p>
                        {p.connected ? (
                          <Badge variant="outline" className="bg-success/10 text-success border-success/20">Подключено</Badge>
                        ) : (
                          <Badge variant="outline">Не подключено</Badge>
                        )}
                        {p.connected && p.is_test && (
                          <Badge variant="outline">{isTbank ? 'Тестовый терминал' : 'Тестовый магазин'}</Badge>
                        )}
                      </div>
                      {p.description && <p className="text-sm text-muted-foreground mt-1">{p.description}</p>}
                    </div>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <span className="text-sm text-muted-foreground">Принимать оплату</span>
                    <Switch
                      checked={p.is_enabled}
                      disabled={busy || !p.connected}
                      onCheckedChange={(v) => post(p.slug, { action: 'toggle', enabled: v }, v ? 'Приём оплаты включён' : 'Приём оплаты выключен')}
                    />
                  </div>
                </div>

                {showForm ? (
                  <TbankTerminalForm
                    terminalKey={p.shop_id}
                    config={p.config || {}}
                    busy={busy}
                    onSave={(body) => post(p.slug, body, 'Терминал Т‑Банка сохранён')}
                    onCancel={p.connected ? () => setEditing(null) : undefined}
                  />
                ) : p.connected ? (
                  <div className="flex flex-col gap-3 rounded-lg border border-border p-4 sm:flex-row sm:items-center sm:justify-between">
                    <div className="text-sm space-y-0.5">
                      <p className="text-foreground">
                        {isTbank ? `Терминал ${p.shop_id || '—'}` : `Магазин № ${p.shop_id || '—'}`}
                        {isTbank && p.config?.receipt_enabled && <span className="text-muted-foreground"> · чек передаётся</span>}
                      </p>
                      <p className="text-muted-foreground">
                        Подключил {p.connected_by || '—'} · {formatDateTime(p.connected_at)}
                      </p>
                    </div>
                    <div className="flex gap-2">
                      <Button variant="outline" size="sm" disabled={busy} onClick={() => check(p.slug)}>
                        <Icon name="Activity" size={14} className="mr-2" />
                        Проверить
                      </Button>
                      {isTbank ? (
                        <Button variant="outline" size="sm" disabled={busy} onClick={() => setEditing(p.slug)}>
                          <Icon name="Pencil" size={14} className="mr-2" />
                          Изменить
                        </Button>
                      ) : (
                        <Button variant="outline" size="sm" disabled={busy} onClick={() => connect(p.slug)}>
                          <Icon name="RefreshCw" size={14} className="mr-2" />
                          Переподключить
                        </Button>
                      )}
                      <Button variant="ghost" size="sm" disabled={busy}
                        onClick={() => post(p.slug, { action: 'disconnect' }, isTbank ? 'Терминал отключён' : 'Магазин отключён')}>
                        Отключить
                      </Button>
                    </div>
                  </div>
                ) : (
                  <div className="flex flex-col gap-3 rounded-lg border border-dashed border-border p-4 sm:flex-row sm:items-center sm:justify-between">
                    <p className="text-sm text-muted-foreground">
                      {p.configured
                        ? 'Войдите в ЮKassa под владельцем магазина платформы и разрешите доступ приложению «Сверка»'
                        : 'Сначала добавьте ключи приложения ЮKassa в секреты проекта'}
                    </p>
                    <Button disabled={busy || !p.configured} onClick={() => connect(p.slug)} className="shrink-0">
                      {busy ? <Icon name="Loader2" size={14} className="animate-spin mr-2" /> : <Icon name="Link" size={14} className="mr-2" />}
                      Подключить
                    </Button>
                  </div>
                )}
                {isTbank && <TbankWebhookUrl />}
                {isTbank && p.connected && <TbankTestPanel />}
              </CardContent>
            </Card>
          );
        })}
      </div>

      <AdminSubscriptionTransactions />
    </div>
  );
};

export default AdminPaymentProvidersSection;
