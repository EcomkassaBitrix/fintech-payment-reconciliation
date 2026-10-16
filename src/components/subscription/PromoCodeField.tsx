import { useEffect, useState } from 'react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import Icon from '@/components/ui/icon';
import { useToast } from '@/hooks/use-toast';
import { formatLongDate } from '@/lib/subscription';
import functionUrls from '../../../backend/func2url.json';
import { couponPeriodLabel } from '@/lib/couponPeriod';

interface CouponInfo {
  code: string;
  tariff_name: string;
  period: string;
  period_end?: string;
}

interface Props {
  companyId: number;
  canApply: boolean;
  onApplied: () => void;
}

const api = (functionUrls as Record<string, string>)['subscription-checkout'];

const call = async (action: string, companyId: number, code: string) => {
  const res = await fetch(api, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action, company_id: companyId, code })
  });
  const data = await res.json();
  return res.ok && data.success ? { coupon: data.coupon as CouponInfo } : { error: (data.error as string) || 'Не удалось проверить' };
};

const PromoCodeField = ({ companyId, canApply, onApplied }: Props) => {
  const { toast } = useToast();
  const [code, setCode] = useState('');
  const [checking, setChecking] = useState(false);
  const [applying, setApplying] = useState(false);
  const [valid, setValid] = useState<CouponInfo | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setValid(null);
    setError(null);
    const value = code.trim();
    if (value.length < 3) return;
    let cancelled = false;
    setChecking(true);
    const t = setTimeout(async () => {
      const r = await call('coupon_check', companyId, value).catch(() => ({ error: 'Ошибка подключения' }));
      if (cancelled) return;
      setChecking(false);
      if ('coupon' in r && r.coupon) setValid(r.coupon);
      else setError(r.error || 'Промокод не подходит');
    }, 500);
    return () => {
      cancelled = true;
      clearTimeout(t);
      setChecking(false);
    };
  }, [code, companyId]);

  const apply = async () => {
    setApplying(true);
    const r = await call('coupon_apply', companyId, code.trim()).catch(() => ({ error: 'Ошибка подключения' }));
    setApplying(false);
    if ('coupon' in r && r.coupon) {
      toast({
        title: `Промокод применён: тариф «${r.coupon.tariff_name}»`,
        description: r.coupon.period_end ? `Подписка действует до ${formatLongDate(r.coupon.period_end)}` : undefined
      });
      setCode('');
      onApplied();
    } else {
      setError(r.error || 'Не удалось применить');
    }
  };

  if (!canApply) return null;

  return (
    <div className="w-full sm:w-80">
      <div className="flex gap-2">
        <div className="relative flex-1">
          <Icon name="Ticket" size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={code}
            onChange={(e) => setCode(e.target.value.toUpperCase())}
            placeholder="Промокод"
            className="pl-9 pr-8 font-mono uppercase"
          />
          {checking && (
            <Icon name="Loader2" size={14} className="absolute right-3 top-1/2 -translate-y-1/2 animate-spin text-muted-foreground" />
          )}
          {valid && !checking && (
            <Icon name="CircleCheck" size={16} className="absolute right-3 top-1/2 -translate-y-1/2 text-primary" />
          )}
        </div>
        {valid && (
          <Button onClick={apply} disabled={applying}>
            {applying ? <Icon name="Loader2" size={16} className="animate-spin" /> : 'Применить'}
          </Button>
        )}
      </div>
      {valid && (
        <p className="mt-1.5 text-xs text-primary">
          Тариф «{valid.tariff_name}» на {couponPeriodLabel(valid.period)} бесплатно
        </p>
      )}
      {error && <p className="mt-1.5 text-xs text-destructive">{error}</p>}
    </div>
  );
};

export default PromoCodeField;
