import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import Icon from '@/components/ui/icon';

const plural = (n: number) => {
  const m10 = n % 10, m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return 'платёж';
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return 'платежа';
  return 'платежей';
};

interface ProviderStats {
  amount: number;
  count: number;
  commission?: number;
}

interface ReconciliationByProviderProps {
  paymentsByProvider: Record<string, ProviderStats>;
}

const formatMoney = (value: number) =>
  value.toLocaleString('ru-RU', { style: 'currency', currency: 'RUB', minimumFractionDigits: 0 });

const ReconciliationByProvider = ({ paymentsByProvider }: ReconciliationByProviderProps) => {
  const providers = Object.entries(paymentsByProvider).sort((a, b) => b[1].amount - a[1].amount);

  if (providers.length === 0) return null;

  const total = providers.reduce(
    (acc, [, st]) => ({
      amount: acc.amount + st.amount,
      count: acc.count + st.count,
      commission: acc.commission + (st.commission || 0)
    }),
    { amount: 0, count: 0, commission: 0 }
  );
  const formatPercent = (value: number, base: number) =>
    `${((value / base) * 100).toLocaleString('ru-RU', { maximumFractionDigits: 2 })}%`;
  const commissionCell = (value: number, base: number) =>
    value > 0 ? (
      <>
        <div className="text-warning">−{formatMoney(value)}</div>
        {base > 0 && <div className="text-xs text-muted-foreground">{formatPercent(value, base)}</div>}
      </>
    ) : (
      <span className="text-muted-foreground">—</span>
    );

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-start gap-2 text-xl sm:text-2xl leading-tight">
          <Icon name="Wallet" size={20} className="shrink-0 mt-1" />
          Детализация по видам оплат
        </CardTitle>
        <CardDescription>
          Успешные платежи по платёжным интеграциям; для шлюза Екомкассы — по видам оплат (СБП, эквайринг и т.п.)
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="flex items-center gap-4 pb-2 border-b border-border text-xs text-muted-foreground">
          <span className="min-w-0 flex-1">Вид оплаты</span>
          <span className="w-28 shrink-0 text-right">Платежи</span>
          <span className="w-24 shrink-0 text-right">Комиссия</span>
        </div>
        <div>
          {providers.map(([provider, stats]) => (
            <div key={provider} className="flex items-center gap-4 py-3 border-b border-border">
              <span className="min-w-0 flex-1 text-sm text-foreground break-words">{provider}</span>
              <div className="w-28 shrink-0 text-right">
                <div className="text-sm font-medium text-foreground whitespace-nowrap">{formatMoney(stats.amount)}</div>
                <div className="text-xs text-muted-foreground whitespace-nowrap">{stats.count} {plural(stats.count)}</div>
              </div>
              <div className="w-24 shrink-0 text-right text-sm whitespace-nowrap">{commissionCell(stats.commission || 0, stats.amount)}</div>
            </div>
          ))}
          <div className="flex items-center gap-4 pt-3">
            <span className="min-w-0 flex-1 text-sm font-semibold text-foreground">Итого</span>
            <div className="w-28 shrink-0 text-right">
              <div className="text-sm font-semibold text-foreground whitespace-nowrap">{formatMoney(total.amount)}</div>
              <div className="text-xs text-muted-foreground whitespace-nowrap">{total.count} {plural(total.count)}</div>
            </div>
            <div className="w-24 shrink-0 text-right text-sm font-semibold whitespace-nowrap">{commissionCell(total.commission, total.amount)}</div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
};

export default ReconciliationByProvider;
