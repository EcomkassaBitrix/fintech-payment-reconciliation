import { Button } from '@/components/ui/button';
import Icon from '@/components/ui/icon';
import { UserIntegration } from '@/components/integrations/integrationsPageTypes';

const GROUPS = [
  { slug: 'banks', icon: 'Landmark', name: 'Банк (расчётный счёт)', text: 'Поступления на счёт — для сверки денег с чеками' },
  { slug: 'payments', icon: 'Wallet', name: 'Платёжный сервис', text: 'Эквайринг, ЮKassa, CloudPayments и другие — оплаты клиентов' },
  { slug: 'cash_registers', icon: 'Receipt', name: 'Онлайн-касса', text: 'Через неё пробиваются чеки' }
];

interface Props {
  items: UserIntegration[];
  isLoading: boolean;
  onConnect?: (categorySlug: string) => void;
}

const OnboardingIntegrations = ({ items, isLoading, onConnect }: Props) => (
  <div className="space-y-3">
    {GROUPS.map((g) => {
      const connected = items.filter((i) => i.category_slug === g.slug);
      return (
        <div key={g.slug} className="flex flex-col gap-3 rounded-lg border border-border p-3 sm:flex-row sm:items-center">
          <div className="flex flex-1 gap-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
              <Icon name={g.icon} size={18} />
            </div>
            <div>
              <div className="text-sm font-medium">{g.name}</div>
              <div className="text-xs text-muted-foreground">
                {connected.length ? connected.map((i) => i.integration_name || i.provider_name).join(', ') : g.text}
              </div>
            </div>
          </div>
          {isLoading ? (
            <Icon name="Loader2" size={16} className="animate-spin text-muted-foreground" />
          ) : connected.length ? (
            <div className="flex items-center gap-2">
              <span className="flex items-center gap-1 text-sm text-success">
                <Icon name="CheckCircle" size={16} />
                Подключено
              </span>
              {onConnect && (
                <Button size="sm" variant="ghost" onClick={() => onConnect(g.slug)}>
                  Ещё
                </Button>
              )}
            </div>
          ) : onConnect ? (
            <Button size="sm" className="gap-1.5" onClick={() => onConnect(g.slug)}>
              <Icon name="Plus" size={14} />
              Подключить
            </Button>
          ) : (
            <span className="text-xs text-muted-foreground">Нет доступа к интеграциям</span>
          )}
        </div>
      );
    })}
    <p className="text-xs text-muted-foreground">
      Можно подключить не всё сразу — вернуться к этому можно в разделе «Интеграции».
    </p>
  </div>
);

export default OnboardingIntegrations;
