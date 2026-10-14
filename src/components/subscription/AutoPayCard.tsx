import { Button } from '@/components/ui/button';
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
  onRemoveCard: () => void;
}

const formatExp = (exp?: string | null) => (exp && exp.length === 4 ? `${exp.slice(0, 2)}/${exp.slice(2)}` : exp || '');

const AutoPayCard = ({ autopay, endDate, canPay, busy, onToggle, onRemoveCard }: AutoPayCardProps) => (
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
              Карта {autopay.card.pan}
              {autopay.card.exp_date && ` · до ${formatExp(autopay.card.exp_date)}`}
              {autopay.auto_renew && endDate && ` · следующее списание ${formatLongDate(endDate)}`}
            </div>
          ) : (
            <div className="text-muted-foreground">
              Карта сохранится при первой оплате — дальше подписка будет продлеваться сама
            </div>
          )}
        </div>
      </div>
      {autopay.card && canPay && (
        <div className="flex items-center gap-3">
          <Switch checked={autopay.auto_renew} disabled={busy} onCheckedChange={onToggle} />
          <Button variant="ghost" size="sm" disabled={busy} onClick={onRemoveCard}>
            Удалить карту
          </Button>
        </div>
      )}
    </div>
  </div>
);

export default AutoPayCard;
