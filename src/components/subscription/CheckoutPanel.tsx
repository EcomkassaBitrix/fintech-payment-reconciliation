import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import Icon from '@/components/ui/icon';
import DowngradeKeepPicker, { KeepState, Overage } from '@/components/profile/DowngradeKeepPicker';
import { Period, PlanTariff, money } from './subscriptionTypes';

interface CheckoutPanelProps {
  chosen: PlanTariff;
  isRenewal: boolean;
  period: Period;
  paying: boolean;
  payBlocked: boolean;
  removing: number;
  checking: boolean;
  overage: Overage | null;
  keep: KeepState;
  keepValid: boolean;
  confirmDelete: boolean;
  price: (t: PlanTariff) => number;
  onCancel: () => void;
  onPay: () => void;
  onKeepChange: (keep: KeepState) => void;
  onConfirmDeleteChange: (v: boolean) => void;
  online?: boolean;
  autoRenew?: boolean;
  onAutoRenewChange?: (v: boolean) => void;
}

const CheckoutPanel = ({
  chosen,
  isRenewal,
  period,
  paying,
  payBlocked,
  removing,
  checking,
  overage,
  keep,
  keepValid,
  confirmDelete,
  price,
  onCancel,
  onPay,
  onKeepChange,
  onConfirmDeleteChange,
  online,
  autoRenew,
  onAutoRenewChange
}: CheckoutPanelProps) => (
  <div className="rounded-xl border border-primary/40 bg-primary/5 p-4">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div className="text-sm">
        <div className="font-semibold">
          {isRenewal ? `Продление тарифа «${chosen.name}»` : `Переход на тариф «${chosen.name}»`}
        </div>
        <div className="text-muted-foreground">
          {period === 'year' ? 'На 365 дней' : `На ${chosen.period_days} дн.`}
          {isRenewal ? ' — добавится к текущему сроку' : ' — с сегодняшнего дня'}
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="ghost" onClick={onCancel} disabled={paying}>
          Отмена
        </Button>
        <Button
          onClick={onPay}
          disabled={paying || payBlocked}
          variant={removing > 0 ? 'destructive' : 'default'}
        >
          <Icon
            name={paying ? 'Loader2' : 'CreditCard'}
            size={16}
            className={`mr-2 ${paying ? 'animate-spin' : ''}`}
          />
          Оплатить {money(price(chosen))}
        </Button>
      </div>
    </div>

    {online && (
      <div className="mt-3 space-y-2 text-sm">
        <label className="flex cursor-pointer items-center gap-2">
          <Checkbox checked={autoRenew} onCheckedChange={(v) => onAutoRenewChange?.(Boolean(v))} />
          <span>Продлевать автоматически — списывать с этой карты в конце каждого периода</span>
        </label>
        <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <Icon name="ShieldCheck" size={14} />
          <span>
            Оплата на защищённой странице Т‑Банка. Карта сохраняется в банке, у нас — только последние цифры.{' '}
            <a href="/payment" target="_blank" rel="noopener noreferrer" className="text-primary hover:underline">
              Условия оплаты и возврата
            </a>
          </span>
        </div>
      </div>
    )}

    {checking && (
      <div className="mt-3 flex items-center gap-2 text-sm text-muted-foreground">
        <Icon name="Loader2" size={14} className="animate-spin" />
        Проверяем лимиты тарифа…
      </div>
    )}

    {overage && (
      <div className="mt-4 space-y-4">
        <div className="flex items-start gap-3 rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-sm">
          <Icon name="TriangleAlert" size={20} className="mt-0.5 shrink-0 text-destructive" />
          <div>
            <div className="font-semibold text-foreground">
              В тариф «{chosen.name}» помещается не всё, что есть сейчас
            </div>
            <div className="text-muted-foreground">
              Отметьте, что оставить. Всё неотмеченное будет удалено безвозвратно при оплате — восстановить
              это будет нельзя, даже если потом перейти на тариф выше.
            </div>
          </div>
        </div>

        <DowngradeKeepPicker overage={overage} keep={keep} onChange={onKeepChange} />

        {removing > 0 && (
          <label className="flex cursor-pointer items-start gap-3 rounded-lg border border-destructive/40 p-3 text-sm">
            <Checkbox
              checked={confirmDelete}
              onCheckedChange={(v) => onConfirmDeleteChange(Boolean(v))}
              className="mt-0.5"
            />
            <span>
              Понимаю, что <span className="font-semibold text-destructive">{removing}</span>{' '}
              {removing === 1 ? 'элемент будет удалён' : 'элементов будут удалены'} навсегда вместе со всеми
              данными
            </span>
          </label>
        )}
        {!keepValid && (
          <div className="text-sm text-destructive">Отмечено больше, чем позволяет тариф.</div>
        )}
      </div>
    )}
  </div>
);

export default CheckoutPanel;
