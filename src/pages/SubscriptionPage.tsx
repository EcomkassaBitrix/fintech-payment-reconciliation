import { useEffect, useRef, useState } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { Button } from '@/components/ui/button';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { useToast } from '@/hooks/use-toast';
import { SUBSCRIPTION_STATUS, subscriptionEndDate, daysLeft, formatLongDate } from '@/lib/subscription';
import functionUrls from '../../backend/func2url.json';
import {
  KeepState,
  Overage,
  initialKeep,
  keepIsValid,
  removalCount
} from '@/components/profile/DowngradeKeepPicker';
import { AutoPay, CurrentPlan, Payment, Period, PlanTariff } from '@/components/subscription/subscriptionTypes';
import AutoPayCard from '@/components/subscription/AutoPayCard';
import { openPaymentPage } from '@/lib/openPayment';
import LinkedCardRow from '@/components/subscription/LinkedCardRow';
import PaymentResultDialog, { PaymentResultState } from '@/components/subscription/PaymentResultDialog';
import CurrentPlanCard from '@/components/subscription/CurrentPlanCard';
import TariffPlansSection from '@/components/subscription/TariffPlansSection';
import CheckoutPanel from '@/components/subscription/CheckoutPanel';
import PaymentResultAndHistory from '@/components/subscription/PaymentResultAndHistory';
import PromoCodeField from '@/components/subscription/PromoCodeField';
import { SUBSCRIPTION_CHANGED } from '@/lib/pendingPromo';

interface SubscriptionPageProps {
  highlightModule?: string | null;
}

const SubscriptionPage = ({ highlightModule }: SubscriptionPageProps) => {
  const { currentCompany, refreshCompanies } = useAuth();
  const { toast } = useToast();
  const [tariffs, setTariffs] = useState<PlanTariff[]>([]);
  const [payments, setPayments] = useState<Payment[]>([]);
  const [canPay, setCanPay] = useState(false);
  const [canCoupon, setCanCoupon] = useState(false);
  const [current, setCurrent] = useState<CurrentPlan | null>(null);
  const [period, setPeriod] = useState<Period>('month');
  const [selected, setSelected] = useState<string | null>(null);
  const [planSheet, setPlanSheet] = useState(Boolean(highlightModule));
  const [paying, setPaying] = useState(false);
  const [paid, setPaid] = useState<{ title: string; until: string } | null>(null);
  const [payError, setPayError] = useState<string | null>(null);
  const resultRef = useRef<HTMLDivElement>(null);
  const [overage, setOverage] = useState<Overage | null>(null);
  const [checking, setChecking] = useState(false);
  const [keep, setKeep] = useState<KeepState>({});
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [provider, setProvider] = useState<string | null>(null);
  const [autopay, setAutopay] = useState<AutoPay | null>(null);
  const [recurringConsent, setRecurringConsent] = useState(false);
  const [autopayBusy, setAutopayBusy] = useState(false);
  const [result, setResult] = useState<PaymentResultState | null>(null);
  const [paymentLink, setPaymentLink] = useState<{ url: string; id: number } | null>(null);
  const [payCheck, setPayCheck] = useState(0);

  useEffect(() => {
    if (paid || payError) resultRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }, [paid, payError]);

  const companyId = currentCompany?.id;

  const load = () => {
    if (!companyId) return;
    fetch(`${functionUrls['subscription-checkout']}?company_id=${companyId}`)
      .then((r) => r.json())
      .then((d) => {
        if (!d.success) return;
        setTariffs(d.tariffs || []);
        setPayments(d.payments || []);
        setCanPay(Boolean(d.can_pay));
        setCanCoupon(Boolean(d.can_coupon ?? d.can_pay));
        setCurrent(d.current || null);
        setProvider(d.provider || null);
        setAutopay(d.autopay || null);
      })
      .catch(() => undefined);
  };

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const returned = params.get('sp');
    if (!returned || !companyId) return;
    params.delete('sp');
    const rest = params.toString();
    window.history.replaceState(null, '', `${window.location.pathname}${rest ? `?${rest}` : ''}`);
    let attempts = 0;
    setResult({ kind: 'checking' });
    const poll = async () => {
      attempts += 1;
      try {
        const res = await fetch(functionUrls['subscription-checkout'], {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ action: 'payment_status', company_id: companyId, payment_id: Number(returned) })
        });
        const d = await res.json();
        const pay = d.payment;
        if (pay?.status === 'paid') {
          const until = formatLongDate(pay.period_end);
          setPaid({ title: `Оплата принята, тариф «${pay.tariff_name}» оплачен`, until });
          setResult({ kind: 'success', tariffName: pay.tariff_name, amount: pay.amount, until, cardSaved: Boolean(pay.card_saved) });
          await refreshCompanies();
          load();
          return;
        }
        if (pay?.status === 'failed' || pay?.status === 'canceled') {
          setPayError(pay.error || 'Банк отклонил оплату');
          setResult({ kind: 'fail', reason: pay.error });
          load();
          return;
        }
      } catch {
        /* повторим */
      }
      if (attempts < 8) setTimeout(poll, 2500);
      else {
        setPayError('Банк ещё не подтвердил оплату. Если деньги списались, тариф включится автоматически в течение нескольких минут.');
        setResult({ kind: 'pending' });
        load();
      }
    };
    poll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [companyId, payCheck]);

  const updateAutopay = async (body: Record<string, unknown>, success: string) => {
    if (!companyId) return;
    setAutopayBusy(true);
    try {
      const res = await fetch(functionUrls['subscription-checkout'], {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...body, company_id: companyId })
      });
      const d = await res.json();
      if (d.success) {
        setAutopay(d.autopay);
        toast({ title: success });
      } else {
        toast({ title: 'Не получилось', description: d.error, variant: 'destructive' });
      }
    } catch {
      toast({ title: 'Ошибка подключения', variant: 'destructive' });
    } finally {
      setAutopayBusy(false);
    }
  };

  useEffect(() => {
    const reload = () => load();
    window.addEventListener(SUBSCRIPTION_CHANGED, reload);
    return () => window.removeEventListener(SUBSCRIPTION_CHANGED, reload);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [companyId]);

  useEffect(() => {
    setSelected(null);
    setPaid(null);
    setPayError(null);
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [companyId]);

  const status = SUBSCRIPTION_STATUS[currentCompany?.subscription_status || ''] || {
    label: currentCompany?.subscription_status || 'Нет подписки',
    className: 'bg-muted text-muted-foreground border-border'
  };
  const isTrial = currentCompany?.subscription_status === 'trial';
  const endDate = subscriptionEndDate(currentCompany);
  const left = daysLeft(endDate);
  const currentSlug = currentCompany?.tariff_slug;
  const currentPaid = tariffs.find((t) => t.slug === currentSlug);
  const chosen = tariffs.find((t) => t.slug === selected) || null;
  const isRenewal = Boolean(chosen && chosen.slug === currentSlug && !isTrial);

  useEffect(() => {
    setOverage(null);
    setKeep({});
    setConfirmDelete(false);
    if (!selected || !companyId) return;
    let cancelled = false;
    setChecking(true);
    fetch(functionUrls['subscription-checkout'], {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'preview', company_id: companyId, tariff_slug: selected })
    })
      .then((r) => r.json())
      .then((d) => {
        if (cancelled || !d.success) return;
        const over: Overage = d.overage || {};
        if (Object.keys(over).length) {
          setOverage(over);
          setKeep(initialKeep(over));
        }
      })
      .catch(() => undefined)
      .finally(() => !cancelled && setChecking(false));
    return () => {
      cancelled = true;
    };
  }, [selected, companyId]);

  const removing = overage ? removalCount(overage, keep) : 0;
  const keepValid = !overage || keepIsValid(overage, keep);
  const payBlocked = checking || !keepValid || (removing > 0 && !confirmDelete);

  const pay = async () => {
    if (!chosen || !companyId) return;
    setPaying(true);
    setPayError(null);
    setPaid(null);
    try {
      const res = await fetch(functionUrls['subscription-checkout'], {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action: 'pay',
          company_id: companyId,
          tariff_slug: chosen.slug,
          period,
          keep: overage ? keep : undefined,
          auto_renew: recurringConsent,
          recurring_consent: recurringConsent
        })
      });
      const data = await res.json().catch(() => ({}));
      if (res.ok && data.success && data.payment_url) {
        const opened = openPaymentPage(data.payment_url);
        setPaymentLink({ url: data.payment_url, id: data.payment_id });
        setPlanSheet(false);
        if (!opened) toast({ title: 'Браузер заблокировал новую вкладку', description: 'Нажмите «Перейти к оплате»' });
        return;
      }
      const message = data.error || `Сервер ответил ошибкой (${res.status})`;
      setPayError(message);
      toast({ title: 'Не удалось оплатить', description: message, variant: 'destructive' });
    } catch {
      setPayError('Нет связи с сервером, попробуйте ещё раз');
      toast({ title: 'Ошибка подключения', variant: 'destructive' });
    } finally {
      setPaying(false);
    }
  };

  const price = (t: PlanTariff) => (period === 'year' ? t.year_price : t.price);

  return (
    <div className="max-w-5xl space-y-6 animate-fade-in">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 className="mb-2 text-2xl sm:text-3xl font-display font-bold text-foreground">Подписка</h2>
          <p className="text-muted-foreground">
            {currentCompany ? 'Тариф, оплата и история платежей' : 'Компания не выбрана'}
          </p>
        </div>
        {currentCompany && canCoupon && (
          <PromoCodeField
            companyId={currentCompany.id}
            canApply
            onApplied={async () => {
              await refreshCompanies();
              load();
            }}
          />
        )}
      </div>

        {currentCompany && (
          <div className="space-y-6 py-2">
            <CurrentPlanCard
              tariffName={currentCompany.tariff_name}
              status={status}
              isTrial={isTrial}
              endDate={endDate}
              left={left}
              canPay={canPay}
              currentPaid={currentPaid}
              onRenew={(slug) => {
                setSelected(slug);
                setPlanSheet(true);
              }}
              onChangePlan={() => {
                setSelected(null);
                setPlanSheet(true);
              }}
            />

            {autopay?.card && (
              <LinkedCardRow
                pan={autopay.card.pan}
                provider={autopay.card.provider}
                canManage={canCoupon}
                busy={autopayBusy}
                onRemove={() => updateAutopay({ action: 'remove_card' }, 'Карта отвязана')}
              />
            )}

            {provider === 'tbank' && autopay?.card && !isTrial && (
              <AutoPayCard
                autopay={autopay}
                endDate={endDate}
                canPay={canPay}
                busy={autopayBusy}
                onToggle={(v) => updateAutopay({ action: 'autopay', enabled: v }, v ? 'Автопродление включено' : 'Автопродление выключено')}
                onRemoveCard={() => updateAutopay({ action: 'remove_card' }, 'Карта удалена')}
              />
            )}

            <PaymentResultAndHistory paid={paid} payError={payError} resultRef={resultRef} payments={payments} />
          </div>
        )}
      {paymentLink && (
        <div className="fixed inset-x-4 bottom-4 z-50 mx-auto flex max-w-xl flex-col gap-3 rounded-xl border border-primary/40 bg-card p-4 shadow-2xl sm:flex-row sm:items-center">
          <div className="flex-1 text-sm">
            <div className="font-semibold text-foreground">Оплата открыта на странице Т‑Банка</div>
            <div className="text-muted-foreground">Оплатите во вкладке банка, затем нажмите «Я оплатил».</div>
          </div>
          <div className="flex gap-2">
            <Button asChild variant="outline" size="sm">
              <a href={paymentLink.url} target="_blank" rel="noopener noreferrer">Перейти к оплате</a>
            </Button>
            <Button
              size="sm"
              onClick={() => {
                const params = new URLSearchParams(window.location.search);
                params.set('sp', String(paymentLink.id));
                window.history.replaceState(null, '', `${window.location.pathname}?${params}`);
                setPaymentLink(null);
                setPayCheck((n) => n + 1);
              }}
            >
              Я оплатил
            </Button>
          </div>
        </div>
      )}

      <Sheet
        open={planSheet}
        onOpenChange={(o) => {
          setPlanSheet(o);
          if (!o) setSelected(null);
        }}
      >
        <SheetContent side="bottom" className="max-h-[90vh] overflow-y-auto">
          <div className="mx-auto w-full max-w-5xl space-y-6 pb-4">
            <SheetHeader>
              <SheetTitle>{isRenewal ? 'Продление тарифа' : 'Выбор тарифа'}</SheetTitle>
            </SheetHeader>
                <TariffPlansSection
                  tariffs={tariffs}
                  current={current}
                  currentSlug={currentSlug}
                  isTrial={isTrial}
                  selected={selected}
                  period={period}
                  canPay={canPay}
                  highlightModule={highlightModule}
                  price={price}
                  onPeriodChange={setPeriod}
                  onSelect={setSelected}
                />

                {chosen && canPay && (
                  <CheckoutPanel
                    chosen={chosen}
                    isRenewal={isRenewal}
                    period={period}
                    paying={paying}
                    payBlocked={payBlocked}
                    removing={removing}
                    checking={checking}
                    overage={overage}
                    keep={keep}
                    keepValid={keepValid}
                    confirmDelete={confirmDelete}
                    price={price}
                    onCancel={() => {
                  setSelected(null);
                  setPlanSheet(false);
                }}
                    onPay={pay}
                    onKeepChange={setKeep}
                    onConfirmDeleteChange={setConfirmDelete}
                    online={provider === 'tbank'}
                    recurringConsent={recurringConsent}
                    onRecurringConsentChange={setRecurringConsent}
                  />
                )}
          </div>
        </SheetContent>
      </Sheet>

      <PaymentResultDialog
        state={result}
        onClose={() => setResult(null)}
        onRetry={() => {
          setResult(null);
          setPayError(null);
          window.scrollTo({ top: 0, behavior: 'smooth' });
        }}
      />
    </div>
  );
};

export default SubscriptionPage;