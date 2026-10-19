import Icon from '@/components/ui/icon';
import { useAuth } from '@/contexts/AuthContext';
import { formatLongDate, subscriptionEndDate } from '@/lib/subscription';

const SubscriptionBlockedNotice = () => {
  const { currentCompany } = useAuth();
  const endDate = subscriptionEndDate(currentCompany);
  const canPay = !currentCompany?.support_access
    && (currentCompany?.role_slug === 'owner' || currentCompany?.role_slug === 'admin');

  return (
    <div className="mb-6 flex items-start gap-3 rounded-xl border border-destructive/40 bg-destructive/10 p-4">
      <Icon name="Lock" size={20} className="mt-0.5 shrink-0 text-destructive" />
      <div className="min-w-0">
        <p className="font-semibold text-foreground">
          {endDate ? `Подписка закончилась ${formatLongDate(endDate)}` : 'Подписка не оформлена'}
        </p>
        <p className="mt-1 text-sm text-muted-foreground">
          Сверка не принимает платежи, чеки и выписки, автоматизации остановлены. Данные за время без подписки не
          загружаются.{' '}
          {canPay
            ? 'Оплатите подписку, чтобы снова открыть кабинет и продолжить сбор данных.'
            : 'Оплатить подписку может владелец или администратор компании — обратитесь к нему.'}
        </p>
      </div>
    </div>
  );
};

export default SubscriptionBlockedNotice;