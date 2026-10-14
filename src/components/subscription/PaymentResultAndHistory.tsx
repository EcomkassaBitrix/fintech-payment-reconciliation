import { RefObject } from 'react';
import Icon from '@/components/ui/icon';
import { formatLongDate } from '@/lib/subscription';
import { PAYMENT_METHODS, Payment, money } from './subscriptionTypes';

interface PaymentResultAndHistoryProps {
  paid: { title: string; until: string } | null;
  payError: string | null;
  resultRef: RefObject<HTMLDivElement>;
  payments: Payment[];
}

const PaymentResultAndHistory = ({ paid, payError, resultRef, payments }: PaymentResultAndHistoryProps) => (
  <>
    {paid && (
      <div ref={resultRef} />
    )}
    {paid && (
      <div className="flex items-start gap-3 rounded-xl border border-success/40 bg-success/10 p-4">
        <Icon name="CircleCheck" size={22} className="mt-0.5 shrink-0 text-success" />
        <div className="text-sm">
          <div className="font-semibold text-foreground">{paid.title}</div>
          <div className="text-muted-foreground">
            Срок действия: до <span className="font-medium text-foreground">{paid.until}</span>
          </div>
        </div>
      </div>
    )}
    {payError && <div ref={resultRef} />}
    {payError && (
      <div className="flex items-start gap-3 rounded-xl border border-destructive/40 bg-destructive/10 p-4 text-sm">
        <Icon name="CircleAlert" size={22} className="mt-0.5 shrink-0 text-destructive" />
        <div>
          <div className="font-semibold text-foreground">Не удалось оплатить</div>
          <div className="text-muted-foreground">{payError}</div>
        </div>
      </div>
    )}
    {payments.length > 0 && (
      <div>
        <h3 className="mb-2 font-semibold">История оплат</h3>
        <div className="divide-y divide-border rounded-lg border border-border">
          {payments.map((p) => {
            const m = PAYMENT_METHODS[p.method || 'manual'] || { label: p.method || '—', icon: 'CreditCard' };
            const isGrant = p.method === 'platform';
            const failed = p.status === 'failed';
            const pending = p.status === 'pending';
            return (
              <div key={p.id} className="flex flex-wrap items-center justify-between gap-2 px-4 py-2.5 text-sm">
                <div>
                  <div>
                    {formatLongDate(p.created_at)} · {p.tariff_name} ·{' '}
                    {p.period === 'year' ? 'год' : 'месяц'}
                  </div>
                  <div className={`flex items-center gap-1 text-xs ${isGrant ? 'text-primary' : 'text-muted-foreground'}`}>
                    <Icon name={m.icon} size={12} />
                    {p.is_recurring ? 'Автопродление' : m.label}
                    {failed && <span className="text-destructive">· не прошла{p.error ? `: ${p.error}` : ''}</span>}
                    {pending && <span className="text-warning">· ожидает оплаты</span>}
                    {p.period_end && <span className="text-muted-foreground">· до {formatLongDate(p.period_end)}</span>}
                  </div>
                </div>
                <span className={`font-medium ${failed ? 'text-muted-foreground line-through' : ''}`}>{isGrant ? 'Бесплатно' : money(p.amount)}</span>
              </div>
            );
          })}
        </div>
      </div>
    )}
  </>
);

export default PaymentResultAndHistory;
