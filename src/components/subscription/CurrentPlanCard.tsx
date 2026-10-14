import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import Icon from '@/components/ui/icon';
import { formatLongDate } from '@/lib/subscription';
import { PlanTariff } from './subscriptionTypes';

interface CurrentPlanCardProps {
  tariffName?: string | null;
  status: { label: string; className: string };
  isTrial: boolean;
  endDate?: string | null;
  left: number | null;
  canPay: boolean;
  currentPaid?: PlanTariff;
  onRenew: (slug: string) => void;
  onChangePlan: () => void;
}

const CurrentPlanCard = ({ tariffName, status, isTrial, endDate, left, canPay, currentPaid, onRenew, onChangePlan }: CurrentPlanCardProps) => (
  <div className="rounded-lg border border-border bg-muted/30 p-4">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div>
        <div className="text-xs text-muted-foreground">Текущий тариф</div>
        <div className="text-xl font-display font-bold">{tariffName || '—'}</div>
      </div>
      <Badge variant="outline" className={status.className}>
        {status.label}
      </Badge>
    </div>
    <div className="mt-3 flex flex-wrap items-center justify-between gap-3 text-sm">
      <span className="text-muted-foreground">
        {isTrial ? 'Пробный период до' : 'Оплачено до'}:{' '}
        <span className="font-medium text-foreground">{formatLongDate(endDate)}</span>
        {left !== null && (
          <span className={`ml-2 font-medium ${left <= 3 ? 'text-warning' : 'text-primary'}`}>
            {left > 0 ? `(осталось дней: ${left})` : '(срок закончился)'}
          </span>
        )}
      </span>
      {canPay && (
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="outline" onClick={onChangePlan}>
            <Icon name="ArrowLeftRight" size={16} className="mr-2" />
            {isTrial || !currentPaid ? 'Выбрать тариф' : 'Сменить тариф'}
          </Button>
          {currentPaid && !isTrial && (
            <Button size="sm" onClick={() => onRenew(currentPaid.slug)}>
              <Icon name="RefreshCw" size={16} className="mr-2" />
              Продлить
            </Button>
          )}
        </div>
      )}
    </div>
  </div>
);

export default CurrentPlanCard;
