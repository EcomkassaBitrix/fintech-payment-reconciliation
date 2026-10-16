import { useMemo, useState } from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import Icon from '@/components/ui/icon';
import { formatLongDate } from '@/lib/subscription';
import { PAYMENT_METHODS, Payment, money } from './subscriptionTypes';
import { couponPeriodLabel } from '@/lib/couponPeriod';

const STATUS: Record<string, { label: string; className: string }> = {
  paid: { label: 'Оплачено', className: 'border-success/40 bg-success/10 text-success' },
  pending: { label: 'Ожидает оплаты', className: 'border-warning/40 bg-warning/10 text-warning' },
  failed: { label: 'Не прошла', className: 'border-destructive/40 bg-destructive/10 text-destructive' },
  canceled: { label: 'Отменена', className: 'border-border bg-muted text-muted-foreground' },
  refunded: { label: 'Возврат', className: 'border-border bg-muted text-muted-foreground' },
  partially_refunded: { label: 'Частичный возврат', className: 'border-border bg-muted text-muted-foreground' }
};

const FILTERS = [
  { key: 'all', label: 'Все' },
  { key: 'paid', label: 'Оплаченные' },
  { key: 'other', label: 'Неуспешные и возвраты' }
] as const;

type FilterKey = (typeof FILTERS)[number]['key'];

const PAGE = 10;

const PaymentsList = ({ payments }: { payments: Payment[] }) => {
  const [filter, setFilter] = useState<FilterKey>('all');
  const [limit, setLimit] = useState(PAGE);

  const list = useMemo(
    () =>
      payments.filter((p) => {
        if (filter === 'paid') return p.status === 'paid';
        if (filter === 'other') return p.status !== 'paid';
        return true;
      }),
    [payments, filter]
  );

  const total = useMemo(
    () =>
      payments.reduce((sum, p) => {
        if (p.method === 'platform') return sum;
        if (p.status === 'paid') return sum + p.amount;
        if (p.status === 'partially_refunded') return sum + p.amount - (p.refund_amount || 0);
        return sum;
      }, 0),
    [payments]
  );

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h3 className="font-semibold">Оплаты</h3>
          <div className="text-sm text-muted-foreground">
            Всего оплачено: <span className="font-medium text-foreground">{money(total)}</span>
          </div>
        </div>
        <div className="inline-flex flex-wrap rounded-lg border border-border p-1">
          {FILTERS.map((f) => (
            <button
              key={f.key}
              onClick={() => {
                setFilter(f.key);
                setLimit(PAGE);
              }}
              className={`rounded-md px-3 py-1 text-sm transition-colors ${
                filter === f.key ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {list.length === 0 ? (
        <div className="rounded-lg border border-dashed border-border p-6 text-center text-sm text-muted-foreground">
          {payments.length === 0 ? 'Оплат пока не было' : 'Нет оплат с таким статусом'}
        </div>
      ) : (
        <div className="divide-y divide-border rounded-lg border border-border">
          {list.slice(0, limit).map((p) => {
            const m = PAYMENT_METHODS[p.method || 'manual'] || { label: p.method || '—', icon: 'CreditCard' };
            const isGrant = p.method === 'platform' || p.method === 'coupon';
            const st = STATUS[p.status || 'paid'] || { label: p.status || '—', className: 'border-border text-muted-foreground' };
            const crossed = ['failed', 'canceled', 'refunded'].includes(p.status || '');
            return (
              <div key={p.id} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 text-sm">
                <div className="min-w-0 space-y-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium text-foreground">
                      {p.tariff_name} · {p.period === 'year' ? 'год' : p.period === 'quarter' || p.period === 'half_year' ? couponPeriodLabel(p.period) : `${p.days || 30} дн.`}
                    </span>
                    <Badge variant="outline" className={st.className}>
                      {st.label}
                    </Badge>
                  </div>
                  <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-muted-foreground">
                    <span>{formatLongDate(p.paid_at || p.created_at)}</span>
                    <span className={`flex items-center gap-1 ${isGrant ? 'text-primary' : ''}`}>
                      <Icon name={p.is_recurring ? 'RefreshCw' : m.icon} size={12} />
                      {p.is_recurring ? 'Автопродление' : p.coupon_code ? `Активирован промокод ${p.coupon_code}` : m.label}
                    </span>
                    {p.status === 'paid' && p.period_end && <span>· действует до {formatLongDate(p.period_end)}</span>}
                    {p.status === 'failed' && p.error && <span className="text-destructive">· {p.error}</span>}
                    {p.refund_amount ? (
                      <span>
                        · возвращено {money(p.refund_amount)}
                        {p.refunded_at ? ` ${formatLongDate(p.refunded_at)}` : ''}
                      </span>
                    ) : null}
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  {p.status === 'pending' && p.payment_url && (
                    <Button asChild size="sm" variant="outline">
                      <a href={p.payment_url} target="_blank" rel="noopener noreferrer">
                        Оплатить
                      </a>
                    </Button>
                  )}
                  <span className={`font-medium ${crossed ? 'text-muted-foreground line-through' : 'text-foreground'}`}>
                    {isGrant ? 'Бесплатно' : money(p.amount)}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {list.length > limit && (
        <Button variant="ghost" size="sm" className="mt-2 w-full" onClick={() => setLimit((n) => n + PAGE)}>
          Показать ещё ({list.length - limit})
        </Button>
      )}
    </div>
  );
};

export default PaymentsList;
