import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import Icon from '@/components/ui/icon';
import { useToast } from '@/hooks/use-toast';
import { useAuth } from '@/contexts/AuthContext';
import functionUrls from '../../../backend/func2url.json';

const urls = functionUrls as Record<string, string>;
const checkout = urls['subscription-checkout'];

const TEST_CARDS = [
  { pan: '2200 7702 3909 7761', note: 'Успешная оплата без 3‑D Secure' },
  { pan: '2201 3820 0000 0013', note: 'Успешная оплата, 3‑D Secure без пароля' },
  { pan: '2201 3820 0000 0047', note: 'Оплата с вводом пароля 3‑D Secure: 1qwezxc' },
  { pan: '2201 3820 0000 0831', note: 'Отказ: недостаточно средств' },
  { pan: '2201 3820 0000 0021', note: 'Отказ: ошибка списания' }
];

interface Option {
  id: number | string;
  name: string;
}

interface TestState {
  id: number;
  status: string;
  tariff_name?: string;
  amount?: number;
  error?: string | null;
}

const STATUS_LABEL: Record<string, string> = {
  pending: 'Ожидает оплаты',
  paid: 'Оплачен',
  failed: 'Не прошёл',
  refunded: 'Возвращён'
};

const selectClass = 'h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground';

const TbankTestPanel = () => {
  const { user } = useAuth();
  const { toast } = useToast();
  const [companies, setCompanies] = useState<Option[]>([]);
  const [tariffs, setTariffs] = useState<{ slug: string; name: string; price: number }[]>([]);
  const [companyId, setCompanyId] = useState('');
  const [tariffSlug, setTariffSlug] = useState('');
  const [busy, setBusy] = useState<string | null>(null);
  const [last, setLast] = useState<TestState | null>(null);

  useEffect(() => {
    if (!user) return;
    fetch(`${urls['admin-companies-list']}?requester_user_id=${user.user_id}`)
      .then((r) => r.json())
      .then((d) => {
        const list: Option[] = (d.companies || []).map((c: Option) => ({ id: c.id, name: c.name }));
        setCompanies(list);
        const test = list.find((c) => /тест/i.test(c.name));
        if (test) setCompanyId(String(test.id));
      })
      .catch(() => undefined);
    fetch(urls['tariffs-list'])
      .then((r) => r.json())
      .then((d) => {
        const paid = (d.tariffs || []).filter((t: { slug: string; price: number }) => t.slug !== 'trial' && t.price > 0);
        setTariffs(paid);
        if (paid[0]) setTariffSlug(paid[0].slug);
      })
      .catch(() => undefined);
  }, [user]);

  const call = async (body: Record<string, unknown>) => {
    const res = await fetch(checkout, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });
    return res.json();
  };

  const checkStatus = async (paymentId: number, silent = false) => {
    setBusy('status');
    try {
      const d = await call({ action: 'test_status', payment_id: paymentId });
      if (d.success) {
        setLast(d.payment);
        if (!silent) toast({ title: `Платёж: ${STATUS_LABEL[d.payment.status] || d.payment.status}`, description: d.payment.error || undefined });
      }
    } finally {
      setBusy(null);
    }
  };

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const tp = params.get('tp');
    if (!tp) return;
    params.delete('tp');
    window.history.replaceState(null, '', `${window.location.pathname}?${params}`);
    setTimeout(() => checkStatus(Number(tp)), 1500);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const startCheckout = async () => {
    setBusy('checkout');
    try {
      const d = await call({ action: 'test_checkout', company_id: Number(companyId), tariff_slug: tariffSlug, period: 'month' });
      if (d.success && d.payment_url) {
        window.location.href = d.payment_url;
        return;
      }
      toast({ title: 'Банк не принял платёж', description: d.error, variant: 'destructive' });
    } catch {
      toast({ title: 'Ошибка подключения', variant: 'destructive' });
    }
    setBusy(null);
  };

  const chargeCard = async () => {
    setBusy('charge');
    try {
      const d = await call({ action: 'test_charge', company_id: Number(companyId) });
      if (d.payment_id) await checkStatus(d.payment_id, true);
      toast({
        title: d.status === 'paid' ? 'Списание по карте прошло' : 'Списание не прошло',
        description: d.error || (d.bank_status ? `Статус банка: ${d.bank_status}` : undefined),
        variant: d.status === 'paid' ? 'default' : 'destructive'
      });
    } catch {
      toast({ title: 'Ошибка подключения', variant: 'destructive' });
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="space-y-4 rounded-lg border border-dashed border-primary/40 bg-primary/5 p-4">
      <div>
        <p className="text-sm font-semibold text-foreground">Тестовый платёж</p>
        <p className="text-xs text-muted-foreground">
          Работает и при выключенном «Принимать оплату». Тариф выбранной компании продлится, карта сохранится.
        </p>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label>Компания</Label>
          <select className={selectClass} value={companyId} onChange={(e) => setCompanyId(e.target.value)}>
            <option value="">Выберите компанию</option>
            {companies.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </div>
        <div className="space-y-1.5">
          <Label>Тариф (на месяц)</Label>
          <select className={selectClass} value={tariffSlug} onChange={(e) => setTariffSlug(e.target.value)}>
            {tariffs.map((t) => <option key={t.slug} value={t.slug}>{t.name} — {t.price} ₽</option>)}
          </select>
        </div>
      </div>
      <div className="flex flex-wrap gap-2">
        <Button disabled={!companyId || !tariffSlug || Boolean(busy)} onClick={startCheckout}>
          <Icon name={busy === 'checkout' ? 'Loader2' : 'CreditCard'} size={14} className={`mr-2 ${busy === 'checkout' ? 'animate-spin' : ''}`} />
          1. Оплатить и сохранить карту
        </Button>
        <Button variant="outline" disabled={!companyId || Boolean(busy)} onClick={chargeCard}>
          <Icon name={busy === 'charge' ? 'Loader2' : 'RefreshCw'} size={14} className={`mr-2 ${busy === 'charge' ? 'animate-spin' : ''}`} />
          2. Списать по сохранённой карте
        </Button>
        {last && (
          <Button variant="ghost" disabled={Boolean(busy)} onClick={() => checkStatus(last.id)}>
            <Icon name="Activity" size={14} className="mr-2" />
            Обновить статус
          </Button>
        )}
      </div>
      {last && (
        <div className="rounded-md border border-border bg-card p-3 text-sm">
          Платёж № {last.id}{last.tariff_name ? ` · ${last.tariff_name}` : ''}{last.amount ? ` · ${last.amount} ₽` : ''} —{' '}
          <span className={last.status === 'paid' ? 'text-success' : last.status === 'failed' ? 'text-destructive' : 'text-warning'}>
            {STATUS_LABEL[last.status] || last.status}
          </span>
          {last.error && <div className="text-xs text-muted-foreground">{last.error}</div>}
        </div>
      )}
      <div className="space-y-1 text-xs text-muted-foreground">
        <p className="font-medium text-foreground">Тестовые карты Т‑Банка (срок 12/30, CVC 123):</p>
        {TEST_CARDS.map((c) => (
          <p key={c.pan}>
            <span className="font-mono text-foreground">{c.pan}</span> — {c.note}
          </p>
        ))}
        <p>Возврат тестового платежа — кнопкой в таблице «Транзакции» ниже.</p>
      </div>
    </div>
  );
};

export default TbankTestPanel;
