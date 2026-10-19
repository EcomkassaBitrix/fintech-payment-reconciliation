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
  receipts: {
    amount: number;
    count: number;
    ofd_amount?: number;
    ofd_count?: number;
    correction_amount?: number;
    correction_count?: number;
  };
  bank: { amount: number; raw_amount: number; commission_amount: number; count: number };
}

interface ReconciliationTilesProps {
  totals: ReconciliationTotals;
  onTileClick?: (typeKey: TypeFilterKey) => void;
  lockedTiles?: Partial<Record<TypeFilterKey, boolean>>;
  onConnectIntegration?: (categorySlug: string) => void;
}

const TILE_CATEGORY: Record<TypeFilterKey, string> = {
  payments: 'payments',
  receipts: 'cash_registers',
  money: 'banks'
} as Record<TypeFilterKey, string>;

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

const ReconciliationTiles = ({ totals, onTileClick, lockedTiles = {}, onConnectIntegration }: ReconciliationTilesProps) => {
  const [lockedKey, setLockedKey] = useState<TypeFilterKey | null>(null);
  const lockOpen = lockedKey !== null;
  const setLockOpen = (open: boolean) => {
    if (!open) setLockedKey(null);
  };
  // Чеки кассы vs чеки ОФД сравниваются по КОЛИЧЕСТВУ документов - это два
  // разных источника одного и того же чека (касса пробивает сама, ОФД
  // получает копию от налоговой), поэтому расхождение в штуках красноречивее
  // расхождения в сумме (пропавший/задвоенный чек виден сразу).
  const ofdCount = totals.receipts.ofd_count;
  const sameMoney = (a: number, b: number) => Math.abs(a - b) < 0.01;
  const kassaCountMatchesOfd = ofdCount !== undefined
    && ofdCount === totals.receipts.count
    && sameMoney(totals.receipts.ofd_amount ?? 0, totals.receipts.amount)
    && sameMoney(totals.payments.amount, totals.receipts.amount);
  const bankVsReceipts = bankVsReceiptsLabel(totals.bank.amount, totals.receipts.amount);

  const isLocked = (typeKey: TypeFilterKey) => !!lockedTiles[typeKey];
  const clickable = (typeKey: TypeFilterKey) =>
    isLocked(typeKey)
      ? {
          role: 'button' as const,
          tabIndex: 0,
          title: 'Данные не загружаются',
          onClick: () => setLockedKey(typeKey),
          onKeyDown: (e: React.KeyboardEvent) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              setLockedKey(typeKey);
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
  const cardClass = (typeKey: TypeFilterKey) => `relative overflow-hidden border-border bg-card group ${
    isLocked(typeKey) || onTileClick ? 'cursor-pointer transition-colors hover:border-primary/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring' : ''
  }`;
  const openHint = (typeKey: TypeFilterKey) => !isLocked(typeKey) && onTileClick ? (
    <Icon
      name="ArrowUpRight"
      size={16}
      className="ml-auto text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100 group-hover:text-primary"
    />
  ) : null;
  const blurClass = (typeKey: TypeFilterKey) => isLocked(typeKey) ? 'blur-md select-none pointer-events-none' : '';
  const lockOverlay = (typeKey: TypeFilterKey) => isLocked(typeKey) ? (
    <div className="absolute inset-0 flex items-center justify-center">
      <div className="flex h-10 w-10 items-center justify-center rounded-full border border-border bg-background/80 text-muted-foreground transition-colors group-hover:text-primary">
        <Icon name="Lock" size={18} />
      </div>
    </div>
  ) : null;

  return (
    <div className="grid grid-cols-[repeat(auto-fit,minmax(240px,1fr))] gap-4">
      <Card className={cardClass('payments')} {...clickable('payments')}>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-2">
            <Icon name="CreditCard" size={16} />
            Платежи
            {openHint('payments')}
          </CardTitle>
        </CardHeader>
        <CardContent className={blurClass('payments')} aria-hidden={isLocked('payments') || undefined}>
          <div className="text-2xl xl:text-3xl font-display font-bold text-foreground whitespace-nowrap">
            {formatMoney(totals.payments.amount)}
          </div>
          <p className="text-xs text-muted-foreground mt-1">
            {totals.payments.count} транзакций
          </p>
        </CardContent>
        {lockOverlay('payments')}
      </Card>

      <Card className={cardClass('receipts')} {...clickable('receipts')}>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-2">
            <Icon name="Receipt" size={16} />
            Чеки
            {openHint('receipts')}
          </CardTitle>
        </CardHeader>
        <CardContent className={blurClass('receipts')} aria-hidden={isLocked('receipts') || undefined}>
          <div className="text-2xl xl:text-3xl font-display font-bold text-foreground whitespace-nowrap">
            {formatMoney(totals.receipts.amount)}
          </div>
          {ofdCount !== undefined && (
            <p className="text-xs mt-1 truncate">
              <span className={kassaCountMatchesOfd ? 'text-success' : 'text-destructive'}>
                {totals.receipts.count} в кассе и {ofdCount} в ОФД
              </span>
              {!!totals.receipts.correction_count && (
                <span
                  className="text-muted-foreground"
                  title={`Чеки коррекции, пробитые позже и учтённые в день оплаты: ${totals.receipts.correction_count} на ${formatMoney(totals.receipts.correction_amount || 0)}`}
                >
                  {' · '}коррекций {totals.receipts.correction_count}
                </span>
              )}
            </p>
          )}
        </CardContent>
        {lockOverlay('receipts')}
      </Card>

      <Card className={cardClass('money')} {...clickable('money')}>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-2">
            <Icon name="Landmark" size={16} />
            Деньги
            {openHint('money')}
          </CardTitle>
        </CardHeader>
        <CardContent className={blurClass('money')} aria-hidden={isLocked('money') || undefined}>
          <div className="text-2xl xl:text-3xl font-display font-bold text-foreground whitespace-nowrap">
            {formatMoney(totals.bank.amount)}
          </div>
          <p className={`text-xs mt-1 ${bankVsReceipts.color}`}>
            {bankVsReceipts.text}
          </p>
        </CardContent>
        {lockOverlay('money')}
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
            {onConnectIntegration && lockedKey ? (
              <Button
                onClick={() => {
                  const slug = TILE_CATEGORY[lockedKey];
                  setLockedKey(null);
                  onConnectIntegration(slug);
                }}
              >
                <Icon name="Plug" size={16} className="mr-2" />
                Подключить интеграцию
              </Button>
            ) : (
              <Button onClick={() => setLockOpen(false)}>Понятно</Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default ReconciliationTiles;