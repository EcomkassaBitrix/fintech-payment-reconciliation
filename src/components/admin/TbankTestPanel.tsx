import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import Icon from '@/components/ui/icon';
import { useToast } from '@/hooks/use-toast';
import { useAuth } from '@/contexts/AuthContext';
import functionUrls from '../../../backend/func2url.json';
import PaymentResultDialog, { PaymentResultState } from '@/components/subscription/PaymentResultDialog';
import { formatLongDate } from '@/lib/subscription';
import { openPaymentPage } from '@/lib/openPayment';

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
  { key: 't1', title: 'Тест 1', name: 'Успешная оплата', card: '2200 7702 3909 7761',
    text: 'Оплата без сохранения карты (Recurrent не передаётся). Ожидаем статус CONFIRMED и уведомление, на которое сервис отвечает OK.' },
  { key: 't2', title: 'Тест 2', name: 'Неуспешная оплата', card: '2201 3820 0000 0831',
    text: 'Оплата картой без денег. Ожидаем отказ (REJECTED) и уведомление, на которое сервис отвечает OK.' },
  { key: 't3', title: 'Тест 3', name: 'Возврат', card: '2200 7702 3909 7761',
    text: 'Сначала успешная оплата, затем полный возврат. Ожидаем статус REFUNDED.' },
  { key: 't7', title: 'Тест 7', name: 'Формирование чека', card: '2200 7702 3909 7761',
    text: 'Успешная оплата с передачей чека: тариф, признак способа и предмета расчёта, НДС, СНО. Нужна включённая передача чека.' },
  { key: 't8', title: 'Тест 8', name: 'Формирование чека возврата', card: '2200 7702 3909 7761',
    text: 'Возврат оплаченного платежа с чеком возврата на возвращаемую сумму. Нужна включённая передача чека.' }
];

const selectClass = 'h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground';

const TbankTestPanel = ({ receiptOn = false }: { receiptOn?: boolean }) => {
  const { user } = useAuth();
  const { toast } = useToast();
  const [companies, setCompanies] = useState<Option[]>([]);
  const [tariffs, setTariffs] = useState<{ slug: string; name: string; price: number }[]>([]);
  const [companyId, setCompanyId] = useState('');
  const [tariffSlug, setTariffSlug] = useState('');
  const [busy, setBusy] = useState<string | null>(null);
  const [last, setLast] = useState<TestState | null>(null);
  const [scenario, setScenario] = useState('t1');
  const [pendingUrl, setPendingUrl] = useState<string | null>(null);
  const [result, setResult] = useState<PaymentResultState | null>(null);

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
    if (!tp) {
      call({ action: 'test_last' })
        .then((d) => d.payment && setLast(d.payment))
        .catch(() => undefined);
      return;
    }
    params.delete('tp');
    window.history.replaceState(null, '', `${window.location.pathname}?${params}`);
    setResult({ kind: 'checking' });
    let attempts = 0;
    const poll = async () => {
      attempts += 1;
      try {
        const d = await call({ action: 'test_status', payment_id: Number(tp) });
        const pay = d.payment;
        if (pay) setLast(pay);
        if (pay?.status === 'paid') {
          setResult({ kind: 'success', tariffName: pay.tariff_name, amount: pay.amount,
            until: pay.period_end ? formatLongDate(pay.period_end) : undefined, cardSaved: Boolean(pay.card_saved) });
          return;
        }
        if (pay?.status === 'failed' || pay?.status === 'canceled') {
          setResult({ kind: 'fail', reason: pay.error });
          return;
        }
      } catch {
        /* повторим */
      }
      if (attempts < 8) setTimeout(poll, 2500);
      else setResult({ kind: 'pending' });
    };
    setTimeout(poll, 1000);
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
        const opened = openPaymentPage(d.payment_url);
        setPendingUrl(d.payment_url);
        await checkStatus(d.payment_id, true);
        toast({
          title: opened ? 'Форма оплаты открыта в новой вкладке' : 'Браузер заблокировал вкладку',
          description: 'Оплатите и нажмите «Обновить статус»'
        });
        setBusy(null);
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
            className={`flex-1 whitespace-nowrap rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
              scenario === sc.key ? 'bg-card text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            {sc.title}
          </button>
        ))}
      </div>
      {(() => {
        const sc = SCENARIOS.find((x) => x.key === scenario)!;
        const needsReceipt = scenario === 't7' || scenario === 't8';
        const isRefund = scenario === 't3' || scenario === 't8';
        const canRefund = last && ['paid', 'partially_refunded'].includes(last.status);
        return (
          <div className="space-y-3">
            <div>
              <p className="text-sm font-semibold text-foreground">{sc.title}. {sc.name}</p>
              <p className="text-xs text-muted-foreground">{sc.text}</p>
              <p className="mt-1 text-xs">
                Карта: <span className="font-mono text-foreground">{sc.card}</span> · 12/30 · CVC 123
              </p>
              {needsReceipt && !receiptOn && (
                <p className="mt-1 text-xs text-destructive">
                  Передача чека выключена — включите её в «Изменить» терминала, иначе тест не пройдёт.
                </p>
              )}
            </div>
            <div className="flex flex-wrap gap-2">
              {(!isRefund || !canRefund) && (
                <Button disabled={!ready || Boolean(busy)} onClick={() => startCheckout('sale')}>
                  <Icon name={busy === 'checkout' ? 'Loader2' : 'CreditCard'} size={14} className={`mr-2 ${busy === 'checkout' ? 'animate-spin' : ''}`} />
                  {isRefund ? '1. Оплатить' : 'Оплатить'}
                </Button>
              )}
              {isRefund && (
                <Button variant="destructive" disabled={!canRefund || Boolean(busy)} onClick={() => cancel()}>
                  <Icon name={busy === 'cancel' ? 'Loader2' : 'Undo2'} size={14} className={`mr-2 ${busy === 'cancel' ? 'animate-spin' : ''}`} />
                  2. Вернуть платёж
                </Button>
              )}
            </div>
          </div>
        );
      })()}

      <details className="text-xs">
        <summary className="cursor-pointer text-muted-foreground">Дополнительно: автоплатёж и отмена</summary>
        <div className="mt-2 flex flex-wrap gap-2">
          <Button size="sm" variant="outline" disabled={!ready || Boolean(busy)} onClick={() => startCheckout('save')}>
            Оплатить и сохранить карту
          </Button>
          <Button size="sm" variant="outline" disabled={!companyId || Boolean(busy)} onClick={chargeCard}>
            Списать по сохранённой карте
          </Button>
          <Button size="sm" variant="outline" disabled={!ready || Boolean(busy)} onClick={() => startCheckout('create')}>
            Создать платёж
          </Button>
          <Button size="sm" variant="outline" disabled={!last || last.status !== 'pending' || Boolean(busy)} onClick={() => cancel()}>
            Отменить неоплаченный
          </Button>
          {pendingUrl && (
            <a href={pendingUrl} target="_blank" rel="noopener noreferrer" className="self-center text-primary hover:underline">
              Форма оплаты
            </a>
          )}
        </div>
      </details>

      {pendingUrl && last?.status === 'pending' && (
        <div className="flex flex-wrap items-center gap-2 rounded-md border border-primary/40 bg-card p-3 text-sm">
          <span className="flex-1">Форма оплаты открыта в новой вкладке. Оплатите и нажмите «Обновить статус».</span>
          <a href={pendingUrl} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline">
            Открыть форму ещё раз
          </a>
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
      <PaymentResultDialog state={result} onClose={() => setResult(null)} />
    </div>
  );
};

export default TbankTestPanel;
