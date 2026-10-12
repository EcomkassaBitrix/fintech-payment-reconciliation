import { useEffect, useState } from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import Icon from '@/components/ui/icon';
import { useToast } from '@/hooks/use-toast';
import functionUrls from '../../../backend/func2url.json';

interface YookassaStatus {
  configured: boolean;
  connected: boolean;
  shop_id: string | null;
  shop: { account_id?: string; test?: boolean; status?: string; fiscalization_enabled?: boolean } | null;
}

const api = `${(functionUrls as Record<string, string>)['tochka-oauth']}?provider=yookassa`;

const YookassaConnectCard = ({ companyId }: { companyId: number }) => {
  const { toast } = useToast();
  const [status, setStatus] = useState<YookassaStatus | null>(null);
  const [busy, setBusy] = useState(false);

  const load = () => {
    fetch(`${api}&action=status&check=1&company_id=${companyId}`)
      .then((r) => r.json())
      .then((d) => setStatus(d))
      .catch(() => undefined);
  };

  useEffect(() => {
    load();
    const params = new URLSearchParams(window.location.search);
    if (params.get('yookassa') === 'connected') {
      toast({ title: 'Магазин ЮKassa подключён' });
      params.delete('yookassa');
      const qs = params.toString();
      window.history.replaceState(null, '', `${window.location.pathname}${qs ? `?${qs}` : ''}`);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [companyId]);

  const connect = async () => {
    setBusy(true);
    try {
      const res = await fetch(`${api}&action=authorize_url&company_id=${companyId}`);
      const data = await res.json();
      if (data.success && data.authorize_url) {
        window.location.href = data.authorize_url;
        return;
      }
      toast({ title: 'Не удалось подключить', description: data.error, variant: 'destructive' });
    } catch {
      toast({ title: 'Ошибка подключения', variant: 'destructive' });
    }
    setBusy(false);
  };

  const disconnect = async () => {
    setBusy(true);
    try {
      const res = await fetch(api, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'disconnect', company_id: companyId })
      });
      const data = await res.json();
      if (data.success) {
        toast({ title: 'Магазин ЮKassa отключён' });
        load();
      } else {
        toast({ title: 'Ошибка', description: data.error, variant: 'destructive' });
      }
    } finally {
      setBusy(false);
    }
  };

  if (!status || !status.configured) return null;

  const shopId = status.shop?.account_id || status.shop_id;

  return (
    <Card className="border-border bg-card">
      <CardContent className="p-5 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-start gap-3">
          <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
            <Icon name="Wallet" size={20} className="text-primary" />
          </div>
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <p className="font-medium text-foreground">ЮKassa</p>
              {status.connected ? (
                <Badge className="bg-success/10 text-success border-success/20" variant="outline">Подключено</Badge>
              ) : (
                <Badge variant="outline">Не подключено</Badge>
              )}
              {status.shop?.test && <Badge variant="outline">Тестовый магазин</Badge>}
            </div>
            <p className="text-sm text-muted-foreground">
              {status.connected
                ? `Магазин${shopId ? ` № ${shopId}` : ''} — доступ выдан через ЮKassa, ключи вводить не нужно`
                : 'Подключите магазин в один клик: войдите в ЮKassa и разрешите доступ (нужна роль Владелец или Управляющий)'}
            </p>
          </div>
        </div>
        {status.connected ? (
          <div className="flex gap-2 shrink-0">
            <Button variant="outline" disabled={busy} onClick={connect}>
              <Icon name="RefreshCw" size={14} className="mr-2" />
              Переподключить
            </Button>
            <Button variant="ghost" disabled={busy} onClick={disconnect}>
              Отключить
            </Button>
          </div>
        ) : (
          <Button disabled={busy} onClick={connect} className="shrink-0">
            {busy ? <Icon name="Loader2" size={14} className="animate-spin mr-2" /> : <Icon name="Link" size={14} className="mr-2" />}
            Подключить ЮKassa
          </Button>
        )}
      </CardContent>
    </Card>
  );
};

export default YookassaConnectCard;
