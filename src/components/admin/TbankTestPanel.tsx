import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
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
  refund_amount?: number | null;
}

const STATUS_LABEL: Record<string, string> = {
  pending: 'Ожидает оплаты',
  paid: 'Оплачен',
  failed: 'Не прошёл',
  canceled: 'Отменён',
  refunded: 'Возвращён',
  partially_refunded: 'Частично возвращён'
};

const SCENARIOS = [
  { key: 'sale', title: 'Продажа', text: 'Обычная оплата картой без сохранения карты. Тариф продлевается, чек продажи уходит в кассу.' },
  { key: 'cancel', title: 'Отмена', text: 'Платёж создаётся и отменяется до оплаты — в банке статус CANCELED, деньги не списываются, чека нет.' },
  { key: 'refund', title: 'Возврат', text: 'Возврат оплаченного платежа — полный или частичный. Касса Т‑Банка формирует чек возврата.' }
];

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
  const [scenario, setScenario] = useState('sale');
  const [refundAmount, setRefundAmount] = useState('');
  const [pendingUrl, setPendingUrl] = useState<string | null>(null);

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

  const startCheckout = async (mode: 'sale' | 'save' | 'create') => {
    setBusy('checkout');
    try {
      const d = await call({
        action: 'test_checkout', company_id: Number(companyId), tariff_slug: tariffSlug, period: 'month',
        scenario: mode === 'save' ? 'save_card' : 'sale'
      });
      if (d.success && d.payment_url) {
        if (mode === 'create') {
          setPendingUrl(d.payment_url);
          await checkStatus(d.payment_id, true);
          toast({ title: 'Платёж создан в банке', description: 'Теперь нажмите «Отменить платёж»' });
          setBusy(null);
          return;
        }
        window.location.href = d.payment_url;
        return;
      }
      toast({ title: 'Банк не принял платёж', description: d.error, variant: 'destructive' });
    } catch {
      toast({ title: 'Ошибка подключения', variant: 'destructive' });
    }
    setBusy(null);
  };

  const cancel = async (amount?: number) => {
    if (!last) return;
    setBusy('cancel');
    try {
      const d = await call({ action: 'test_cancel', payment_id: last.id, amount });
      if (d.payment) setLast(d.payment);
      if (d.success) {
        setPendingUrl(null);
        toast({ title: `Банк: ${d.bank_status}`, description: STATUS_LABEL[d.payment?.status] || undefined });
      } else {
        toast({ title: 'Банк отказал', description: d.error, variant: 'destructive' });
      }
    } catch {
      toast({ title: 'Ошибка подключения', variant: 'destructive' });
    } finally {
      setBusy(null);
    }
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

  const ready = Boolean(companyId && tariffSlug);

  return (
    <div className="space-y-4 rounded-lg border border-dashed border-primary/40 bg-primary/5 p-4">
      <div>
        <p className="text-sm font-semibold text-foreground">Тестовый платёж</p>
        <p className="text-xs text-muted-foreground">
          Работает и при выключенном «Принимать оплату». Оплата продлевает тариф выбранной компании.
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
      <div className="flex flex-wrap gap-1 rounded-lg bg-muted p-1">
        {SCENARIOS.map((sc) => (
          <button
            key={sc.key}
            type="button"
            onClick={() => setScenario(sc.key)}
            className={`flex-1 rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
              scenario === sc.key ? 'bg-card text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            {sc.title}
          </button>
        ))}
      </div>
      <p className="text-xs text-muted-foreground">{SCENARIOS.find((sc) => sc.key === scenario)?.text}</p>

      {scenario === 'sale' && (
        <div className="flex flex-wrap gap-2">
          <Button disabled={!ready || Boolean(busy)} onClick={() => startCheckout('sale')}>
            <Icon name={busy === 'checkout' ? 'Loader2' : 'ShoppingCart'} size={14} className={`mr-2 ${busy === 'checkout' ? 'animate-spin' : ''}`} />
            Оплатить
          </Button>
          <Button variant="outline" disabled={!ready || Boolean(busy)} onClick={() => startCheckout('save')}>
            <Icon name="CreditCard" size={14} className="mr-2" />
            Оплатить и сохранить карту
          </Button>
          <Button variant="outline" disabled={!companyId || Boolean(busy)} onClick={chargeCard}>
            <Icon name={busy === 'charge' ? 'Loader2' : 'RefreshCw'} size={14} className={`mr-2 ${busy === 'charge' ? 'animate-spin' : ''}`} />
            Списать по сохранённой карте
          </Button>
        </div>
      )}

      {scenario === 'cancel' && (
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" disabled={!ready || Boolean(busy)} onClick={() => startCheckout('create')}>
            <Icon name={busy === 'checkout' ? 'Loader2' : 'FilePlus'} size={14} className={`mr-2 ${busy === 'checkout' ? 'animate-spin' : ''}`} />
            1. Создать платёж
          </Button>
          <Button variant="destructive" disabled={!last || last.status !== 'pending' || Boolean(busy)} onClick={() => cancel()}>
            <Icon name={busy === 'cancel' ? 'Loader2' : 'Ban'} size={14} className={`mr-2 ${busy === 'cancel' ? 'animate-spin' : ''}`} />
            2. Отменить платёж
          </Button>
          {pendingUrl && (
            <a href={pendingUrl} target="_blank" rel="noopener noreferrer" className="self-center text-xs text-primary hover:underline">
              Открыть форму оплаты (проверить, что после отмены оплатить нельзя)
            </a>
          )}
        </div>
      )}

      {scenario === 'refund' && (
        <div className="space-y-2">
          {!last || !['paid', 'partially_refunded'].includes(last.status) ? (
            <p className="text-sm text-muted-foreground">
              Сначала проведите оплату во вкладке «Продажа» — затем вернитесь сюда. Возврат любого платежа также доступен в
              таблице «Транзакции».
            </p>
          ) : (
            <div className="flex flex-wrap items-end gap-2">
              <div className="space-y-1.5">
                <Label>Сумма возврата, ₽</Label>
                <Input
                  className="w-40"
                  inputMode="decimal"
                  value={refundAmount}
                  onChange={(e) => setRefundAmount(e.target.value.replace(',', '.').replace(/[^\d.]/g, ''))}
                  placeholder={`${(last.amount || 0) - (last.refund_amount || 0)} (полностью)`}
                />
              </div>
              <Button variant="destructive" disabled={Boolean(busy)} onClick={() => cancel(refundAmount ? Number(refundAmount) : undefined)}>
                <Icon name={busy === 'cancel' ? 'Loader2' : 'Undo2'} size={14} className={`mr-2 ${busy === 'cancel' ? 'animate-spin' : ''}`} />
                {refundAmount ? 'Вернуть частично' : 'Вернуть полностью'}
              </Button>
            </div>
          )}
        </div>
      )}

      {last && (
        <div className="flex">
          <Button variant="ghost" size="sm" disabled={Boolean(busy)} onClick={() => checkStatus(last.id)}>
            <Icon name="Activity" size={14} className="mr-2" />
            Обновить статус
          </Button>
        </div>
      )}
      {last && (
        <div className="rounded-md border border-border bg-card p-3 text-sm">
          Платёж № {last.id}{last.tariff_name ? ` · ${last.tariff_name}` : ''}{last.amount ? ` · ${last.amount} ₽` : ''} —{' '}
          <span className={last.status === 'paid' ? 'text-success' : last.status === 'failed' ? 'text-destructive' : 'text-warning'}>
            {STATUS_LABEL[last.status] || last.status}
          </span>
          {last.refund_amount ? <span className="text-muted-foreground"> · возвращено {last.refund_amount} ₽</span> : null}
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
        <p>Все тестовые платежи с отметкой «тест» видны в таблице «Транзакции» ниже.</p>
      </div>
    </div>
  );
};

export default TbankTestPanel;
