import { RefObject } from 'react';
import Icon from '@/components/ui/icon';
import { Payment } from './subscriptionTypes';
import PaymentsList from './PaymentsList';

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
    <PaymentsList payments={payments} />
  </>
);

export default PaymentResultAndHistory;
