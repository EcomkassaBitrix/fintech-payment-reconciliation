import { useEffect, useRef } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { useToast } from '@/hooks/use-toast';
import { formatLongDate } from '@/lib/subscription';
import { GOALS, reachGoal } from '@/lib/metrika';
import { forgetPromo, pendingPromo, pendingPromoError, SUBSCRIPTION_CHANGED } from '@/lib/pendingPromo';
import functionUrls from '../../backend/func2url.json';

const api = (functionUrls as Record<string, string>)['subscription-checkout'];

const PendingPromoActivator = () => {
  const { user, currentCompany, refreshCompanies } = useAuth();
  const { toast } = useToast();
  const running = useRef(false);
  const companyId = currentCompany?.id;

  useEffect(() => {
    const code = pendingPromo();
    if (!user || !companyId || !code || running.current) return;
    const knownError = pendingPromoError();
    if (knownError) {
      forgetPromo();
      toast({ title: `Промокод ${code} не применён`, description: knownError, variant: 'destructive' });
      return;
    }
    running.current = true;
    (async () => {
      try {
        const res = await fetch(api, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ action: 'coupon_apply', company_id: companyId, code })
        });
        const d = await res.json();
        forgetPromo();
        if (res.ok && d.success) {
          reachGoal(GOALS.promoActivated, {
            source: 'promo_link',
            code,
            tariff_name: d.coupon?.tariff_name,
            company_id: companyId
          });
          toast({
            title: `Промокод ${code} активирован: тариф «${d.coupon.tariff_name}»`,
            description: d.coupon.period_end ? `Подписка действует до ${formatLongDate(d.coupon.period_end)}` : undefined
          });
          await refreshCompanies();
          window.dispatchEvent(new Event(SUBSCRIPTION_CHANGED));
        } else {
          toast({ title: `Промокод ${code} не применён`, description: d.error, variant: 'destructive' });
        }
      } catch {
        toast({ title: 'Не удалось применить промокод', description: 'Введите его в разделе «Подписка»', variant: 'destructive' });
      } finally {
        running.current = false;
      }
    })();
  }, [user, companyId, refreshCompanies, toast]);

  return null;
};

export default PendingPromoActivator;