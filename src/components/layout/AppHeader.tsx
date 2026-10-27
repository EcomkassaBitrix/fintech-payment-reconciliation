import { useNavigate } from "@/lib/router-compat";
import { Button } from '@/components/ui/button';
import Icon from '@/components/ui/icon';
import { useAuth } from '@/contexts/AuthContext';
import { subscriptionEndDate, daysLeft, formatShortDate } from '@/lib/subscription';

interface AppHeaderProps {
  unreadCount: number;
  onShowNotifications: () => void;
  onOpenSubscription?: () => void;
  subscriptionActive?: boolean;
  onOpenMenu?: () => void;
}

const AppHeader = ({ unreadCount, onShowNotifications, onOpenSubscription, subscriptionActive, onOpenMenu }: AppHeaderProps) => {
  const { logout, isPlatformAdmin, currentCompany } = useAuth();
  const endDate = subscriptionEndDate(currentCompany);
  const left = daysLeft(endDate);
  const expired = left !== null && left <= 0;
  const soon = left !== null && left > 0 && left <= 3;
  const navigate = useNavigate();

  return (
    <header className="fixed top-0 left-0 lg:left-64 right-0 h-16 bg-background/95 backdrop-blur-sm border-b border-border z-30 px-3 sm:px-6 lg:px-8 flex items-center justify-between gap-2">
      <div className="flex items-center gap-2 sm:gap-4 min-w-0">
        <Button variant="ghost" size="icon" className="lg:hidden shrink-0" onClick={onOpenMenu} aria-label="Открыть меню">
          <Icon name="Menu" size={22} />
        </Button>
        {currentCompany?.tariff_name && (
          <button
            type="button"
            onClick={onOpenSubscription}
            className={`flex items-center gap-2 sm:gap-3 min-w-0 rounded-lg border px-2.5 sm:px-3 py-1.5 text-left transition-colors hover:border-primary/50 hover:bg-muted/40 ${
              subscriptionActive ? 'border-primary/60 bg-muted/40' : 'border-border'
            }`}
            title="Управление подпиской"
          >
            <Icon name="CreditCard" size={18} className="text-primary shrink-0" />
            <span className="text-sm font-semibold text-foreground truncate">{currentCompany.tariff_name}</span>
            {endDate && (
              <span
                className={`hidden sm:inline text-sm whitespace-nowrap ${
                  expired ? 'text-destructive font-medium' : soon ? 'text-warning font-medium' : 'text-muted-foreground'
                }`}
              >
                {expired
                  ? 'срок закончился'
                  : `до ${formatShortDate(endDate)}`}
              </span>
            )}
          </button>
        )}
      </div>

      <div className="flex items-center gap-2 sm:gap-3 shrink-0">
        {isPlatformAdmin && (
          <Button
            variant="outline"
            size="sm"
            className="gap-2 border-primary/40 text-primary hover:bg-primary/10 hover:text-primary"
            onClick={() => navigate('/admin')}
          >
            <Icon name="ShieldCheck" size={16} />
            <span className="hidden sm:inline">Админка</span>
          </Button>
        )}

        <div className="relative">
          <Button
            variant="outline"
            size="icon"
            onClick={onShowNotifications}
            className="relative"
          >
            <Icon name="Bell" size={20} />
            {unreadCount > 0 && (
              <span className="absolute -top-1 -right-1 w-5 h-5 bg-destructive text-destructive-foreground text-xs rounded-full flex items-center justify-center animate-scale-in">
                {unreadCount}
              </span>
            )}
          </Button>
        </div>

        <Button variant="outline" size="sm" className="gap-2 text-destructive hover:text-destructive" onClick={logout}>
          <Icon name="LogOut" size={16} />
          <span className="hidden sm:inline">Выход</span>
        </Button>
      </div>
    </header>
  );
};

export default AppHeader;