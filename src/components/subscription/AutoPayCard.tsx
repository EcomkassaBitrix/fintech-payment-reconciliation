import { Switch } from '@/components/ui/switch';
import Icon from '@/components/ui/icon';
import { formatLongDate } from '@/lib/subscription';
import { AutoPay } from './subscriptionTypes';

interface AutoPayCardProps {
  autopay: AutoPay;
  endDate?: string | null;
  canPay: boolean;
  busy: boolean;
  onToggle: (enabled: boolean) => void;
  onRemoveCard?: () => void;
}

const AutoPayCard = ({ autopay, endDate, canPay, busy, onToggle }: AutoPayCardProps) => (
  <div className="rounded-lg border border-border p-4">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div className="flex items-start gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10">
          <Icon name="CreditCard" size={20} className="text-primary" />
        </div>
        <div className="text-sm">
          <div className="font-semibold text-foreground">Автопродление</div>
          {autopay.card ? (
            <div className="text-muted-foreground">
              {autopay.auto_renew
                ? `Списание с привязанной карты${endDate ? ` ${formatLongDate(endDate)}` : ''}`
                : 'Выключено — продлевайте подписку вручную'}
            </div>
          ) : (
            <div className="text-muted-foreground">
              Карта сохранится при первой оплате — дальше подписка будет продлеваться сама
            </div>
          )}
        </div>
      </div>
      {autopay.card && canPay && (
        <Switch checked={autopay.auto_renew} disabled={busy} onCheckedChange={onToggle} />
      )}
      {autopay.card && !canPay && (
        <span className="text-xs text-muted-foreground">Включает владелец или админ компании</span>
      )}
    </div>
  </div>
);

export default AutoPayCard;