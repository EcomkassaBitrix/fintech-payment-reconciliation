import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useState } from 'react';
import Icon from '@/components/ui/icon';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle
} from '@/components/ui/dialog';
import { TYPE_FILTERS, TypeFilterKey } from '@/lib/transactionTypeFilter';

interface ReconciliationTotals {
  payments: { amount: number; count: number };
  receipts: { amount: number; count: number; ofd_amount?: number; ofd_count?: number };
  bank: { amount: number; raw_amount: number; commission_amount: number; count: number };
}

interface ReconciliationTilesProps {
  totals: ReconciliationTotals;
  onTileClick?: (typeKey: TypeFilterKey) => void;
  locked?: boolean;
}

const formatMoney = (value: number) =>
  value.toLocaleString('ru-RU', { style: 'currency', currency: 'RUB', minimumFractionDigits: 0 });

// Плитка "Деньги" сравнивается с чеками по СУММЕ (а не количеству, там разные
// единицы - документы vs операции по счёту, включая комиссии отдельными
// строками) - "Всё в порядке" зелёным при совпадении, иначе разница оранжевым
// (это не обязательно ошибка - деньги приходят с опозданием, за прошлый период
// и т.п., поэтому не красный).
const bankVsReceiptsLabel = (bankAmount: number, receiptsAmount: number) => {
  const diff = bankAmount - receiptsAmount;
  if (Math.abs(diff) < 0.01) return { text: 'Всё в порядке', color: 'text-success' };
  const sign = diff > 0 ? '+' : '−';
  return { text: `разница ${sign}${formatMoney(Math.abs(diff))}`, color: 'text-warning' };
};

const ReconciliationTiles = ({ totals, onTileClick, locked = true }: ReconciliationTilesProps) => {
  const [lockOpen, setLockOpen] = useState(false);
  // Чеки кассы vs чеки ОФД сравниваются по КОЛИЧЕСТВУ документов - это два
  // разных источника одного и того же чека (касса пробивает сама, ОФД
  // получает копию от налоговой), поэтому расхождение в штуках красноречивее
  // расхождения в сумме (пропавший/задвоенный чек виден сразу).
  const ofdCount = totals.receipts.ofd_count;
  const kassaCountMatchesOfd = ofdCount !== undefined && ofdCount === totals.receipts.count;
  const bankVsReceipts = bankVsReceiptsLabel(totals.bank.amount, totals.receipts.amount);

  const clickable = (typeKey: TypeFilterKey) =>
    locked
      ? {
          role: 'button' as const,
          tabIndex: 0,
          title: 'Данные не загружаются',
          onClick: () => setLockOpen(true),
          onKeyDown: (e: React.KeyboardEvent) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              setLockOpen(true);
            }
          }
        }
      : onTileClick
      ? {
          role: 'button' as const,
          tabIndex: 0,
          title: `Открыть транзакции за период: ${TYPE_FILTERS[typeKey].label.toLowerCase()}`,
          onClick: () => onTileClick(typeKey),
          onKeyDown: (e: React.KeyboardEvent) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              onTileClick(typeKey);
            }
          }
        }
      : {};
  const cardClass = `relative overflow-hidden border-border bg-card group ${
    locked || onTileClick ? 'cursor-pointer transition-colors hover:border-primary/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring' : ''
  }`;
  const openHint = !locked && onTileClick ? (
    <Icon
      name="ArrowUpRight"
      size={16}
      className="ml-auto text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100 group-hover:text-primary"
    />
  ) : null;
  const blurClass = locked ? 'blur-md select-none pointer-events-none' : '';
  const lockOverlay = locked ? (
    <div className="absolute inset-0 flex items-center justify-center">
      <div className="flex h-10 w-10 items-center justify-center rounded-full border border-border bg-background/80 text-muted-foreground transition-colors group-hover:text-primary">
        <Icon name="Lock" size={18} />
      </div>
    </div>
  ) : null;

  return (
    <div className="grid grid-cols-[repeat(auto-fit,minmax(240px,1fr))] gap-4">
      <Card className={cardClass} {...clickable('payments')}>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-2">
            <Icon name="CreditCard" size={16} />
            Платежи
            {openHint}
          </CardTitle>
        </CardHeader>
        <CardContent className={blurClass} aria-hidden={locked || undefined}>
          <div className="text-2xl xl:text-3xl font-display font-bold text-foreground whitespace-nowrap">
            {formatMoney(totals.payments.amount)}
          </div>
          <p className="text-xs text-muted-foreground mt-1">
            {totals.payments.count} транзакций
          </p>
        </CardContent>
        {lockOverlay}
      </Card>

      <Card className={cardClass} {...clickable('receipts')}>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-2">
            <Icon name="Receipt" size={16} />
            Чеки
            {openHint}
          </CardTitle>
        </CardHeader>
        <CardContent className={blurClass} aria-hidden={locked || undefined}>
          <div className="text-2xl xl:text-3xl font-display font-bold text-foreground whitespace-nowrap">
            {formatMoney(totals.receipts.amount)}
          </div>
          {ofdCount !== undefined && (
            <p className={`text-xs mt-1 ${kassaCountMatchesOfd ? 'text-success' : 'text-destructive'}`}>
              {totals.receipts.count} в кассе и {ofdCount} в ОФД
            </p>
          )}
        </CardContent>
        {lockOverlay}
      </Card>

      <Card className={cardClass} {...clickable('money')}>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-2">
            <Icon name="Landmark" size={16} />
            Деньги
            {openHint}
          </CardTitle>
        </CardHeader>
        <CardContent className={blurClass} aria-hidden={locked || undefined}>
          <div className="text-2xl xl:text-3xl font-display font-bold text-foreground whitespace-nowrap">
            {formatMoney(totals.bank.amount)}
          </div>
          <p className={`text-xs mt-1 ${bankVsReceipts.color}`}>
            {bankVsReceipts.text}, комиссия {formatMoney(totals.bank.commission_amount)}
          </p>
        </CardContent>
        {lockOverlay}
      </Card>

      <Dialog open={lockOpen} onOpenChange={setLockOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <div className="mx-auto mb-2 flex h-12 w-12 items-center justify-center rounded-full bg-muted text-muted-foreground">
              <Icon name="Lock" size={22} />
            </div>
            <DialogTitle className="text-center">Данные не загружаются</DialogTitle>
            <DialogDescription className="text-center">
              Подключите интеграцию, чтобы Сверка могла сверить всю цепочку: от приема платежа до поступления выплаты на р/с
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="sm:justify-center">
            <Button onClick={() => setLockOpen(false)}>Понятно</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default ReconciliationTiles;