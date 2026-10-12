import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, CardContent } from '@/components/ui/card';
import Icon from '@/components/ui/icon';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { useAuth, Company } from '@/contexts/AuthContext';
import { isLockedByTariff, menuModules } from '@/config/modules';
import ProfileDialog from '@/components/profile/ProfileDialog';

interface AppSidebarProps {
  activeModule: string;
  onModuleChange: (moduleId: string) => void;
  open?: boolean;
  onClose?: () => void;
}

const CompanySwitcher = ({ companies, currentCompany, onSelect }: {
  companies: Company[];
  currentCompany: Company | null;
  onSelect: (id: number) => void;
}) => {
  const navigate = useNavigate();

  if (companies.length === 0) return null;

  return (
    <div className="mb-6">
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button className="w-full flex items-center justify-between gap-2 px-3 py-2.5 rounded-lg bg-sidebar-accent border border-sidebar-border hover:bg-sidebar-accent/70 transition-colors">
            <div className="flex items-center gap-2 min-w-0">
              <Icon name="Building2" size={16} className="text-sidebar-foreground/60 shrink-0" />
              <span className="text-sm font-medium text-sidebar-foreground truncate">
                {currentCompany?.name || 'Выберите компанию'}
              </span>
            </div>
            <Icon name="ChevronsUpDown" size={14} className="text-sidebar-foreground/40 shrink-0" />
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="w-56">
          {[
            { label: 'Ваши компании', list: companies.filter((c) => !c.support_access) },
            { label: 'Клиенты (доступ поддержки)', list: companies.filter((c) => c.support_access) }
          ].filter((g) => g.list.length > 0).map((group, gi) => (
            <div key={group.label}>
              {gi > 0 && <DropdownMenuSeparator />}
              <DropdownMenuLabel>{group.label}</DropdownMenuLabel>
              <DropdownMenuSeparator />
              {group.list.map((company) => (
                <DropdownMenuItem
                  key={company.id}
                  onClick={() => onSelect(company.id)}
                  className="flex items-center justify-between gap-2"
                >
                  <span className="flex items-center gap-2 min-w-0">
                    {company.support_access && <Icon name="LifeBuoy" size={14} className="text-info shrink-0" />}
                    <span className="truncate">{company.name}</span>
                  </span>
                  {company.id === currentCompany?.id && (
                    <Icon name="Check" size={14} className="text-primary shrink-0" />
                  )}
                </DropdownMenuItem>
              ))}
            </div>
          ))}
          <DropdownMenuSeparator />
          <DropdownMenuItem onClick={() => navigate('/create-company')}>
            <Icon name="Plus" size={14} className="mr-2" />
            Добавить компанию
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
};

const formatPhone = (phone?: string) => {
  const d = (phone || '').replace(/\D/g, '');
  if (d.length !== 11) return phone || '';
  return `+${d[0]} ${d.slice(1, 4)} ${d.slice(4, 7)}-${d.slice(7, 9)}-${d.slice(9, 11)}`;
};

const UserProfileMenu = ({ onOpenSettings, onOpenSubscription, onOpenNotifications }: { onOpenSettings: () => void; onOpenSubscription: () => void; onOpenNotifications: () => void }) => {
  const { user, currentCompany, logout } = useAuth();
  const [profileOpen, setProfileOpen] = useState(false);
  const displayName = user?.full_name || formatPhone(user?.phone) || 'Пользователь';

  const itemClass = 'gap-3 px-3 py-2.5 text-[15px] cursor-pointer';

  return (
    <div className="absolute bottom-4 left-4 right-4">
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button className="w-full text-left">
            <Card className="bg-sidebar-accent border-sidebar-border hover:bg-sidebar-accent/70 transition-colors cursor-pointer">
              <CardContent className="p-4">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-full bg-primary/20 flex items-center justify-center shrink-0">
                    <Icon name="User" size={20} className="text-primary" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium text-sidebar-foreground truncate">{displayName}</p>
                    <p className="text-xs text-sidebar-foreground/60 truncate">
                      {currentCompany?.role_name || 'Без роли'}
                    </p>
                  </div>
                  <Icon name="ChevronsUpDown" size={14} className="text-sidebar-foreground/40 shrink-0" />
                </div>
              </CardContent>
            </Card>
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent side="top" align="start" sideOffset={8} className="w-72 p-0">
          <div className="flex items-center gap-3 px-4 py-4">
            <div className="w-11 h-11 rounded-xl bg-primary/20 flex items-center justify-center shrink-0">
              <Icon name="User" size={22} className="text-primary" />
            </div>
            <div className="min-w-0">
              <p className="text-[15px] font-semibold truncate">{displayName}</p>
              <p className="text-sm text-muted-foreground truncate">
                {user?.full_name ? formatPhone(user?.phone) : currentCompany?.name || ''}
              </p>
            </div>
          </div>
          <DropdownMenuSeparator className="m-0" />
          <div className="p-1.5">
            <DropdownMenuItem className={itemClass} onSelect={() => setProfileOpen(true)}>
              <Icon name="User" size={18} className="text-muted-foreground" />
              Профиль
            </DropdownMenuItem>
            <DropdownMenuItem className={itemClass} onSelect={onOpenSubscription}>
              <Icon name="CreditCard" size={18} className="text-muted-foreground" />
              Подписка
            </DropdownMenuItem>
            <DropdownMenuItem className={itemClass} onSelect={onOpenNotifications}>
              <Icon name="BellRing" size={18} className="text-muted-foreground" />
              Уведомления
            </DropdownMenuItem>
            <DropdownMenuItem className={itemClass} onSelect={onOpenSettings}>
              <Icon name="Settings" size={18} className="text-muted-foreground" />
              Настройки
            </DropdownMenuItem>
          </div>
          <DropdownMenuSeparator className="m-0" />
          <div className="p-1.5">
            <DropdownMenuItem onSelect={logout} className={`${itemClass} text-destructive focus:text-destructive`}>
              <Icon name="LogOut" size={18} />
              Выйти
            </DropdownMenuItem>
          </div>
        </DropdownMenuContent>
      </DropdownMenu>

      <ProfileDialog open={profileOpen} onOpenChange={setProfileOpen} />
    </div>
  );
};

const AppSidebar = ({ activeModule, onModuleChange, open = false, onClose }: AppSidebarProps) => {
  const { companies, currentCompany, setCurrentCompanyId } = useAuth();
  const select = (moduleId: string) => {
    onModuleChange(moduleId);
    onClose?.();
  };

  return (
    <>
    {open && <div className="fixed inset-0 z-40 bg-black/60 lg:hidden animate-fade-in" onClick={onClose} />}
    <aside
      className={`fixed left-0 top-0 z-50 h-full w-64 bg-sidebar border-r border-sidebar-border p-4 transition-transform duration-300 lg:translate-x-0 ${
        open ? 'translate-x-0' : '-translate-x-full'
      }`}
    >
      <button
        type="button"
        onClick={onClose}
        aria-label="Закрыть меню"
        className="lg:hidden absolute top-4 right-3 p-1.5 rounded-md text-sidebar-foreground/60 hover:text-sidebar-foreground hover:bg-sidebar-accent/50"
      >
        <Icon name="X" size={20} />
      </button>
      <div className="mb-6">
        <h1 className="text-2xl font-display font-bold text-primary flex items-center gap-2">
          <Icon name="Zap" size={28} />
          Сверка
        </h1>
        <p className="text-sm text-sidebar-foreground/60 mt-1">Платформа сверки 54-ФЗ</p>
      </div>

      <CompanySwitcher
        companies={companies}
        currentCompany={currentCompany}
        onSelect={setCurrentCompanyId}
      />

      <nav className="space-y-2">
        {menuModules(currentCompany).map((module) => {
          const locked = isLockedByTariff(currentCompany, module.id);
          return (
            <button
              key={module.id}
              onClick={() => select(module.id)}
              className={`w-full flex items-center gap-3 px-4 py-3 rounded-lg transition-all duration-200 ${
                activeModule === module.id
                  ? 'bg-sidebar-accent text-sidebar-accent-foreground shadow-lg scale-105'
                  : 'text-sidebar-foreground hover:bg-sidebar-accent/50'
              } ${locked ? 'opacity-60' : ''}`}
            >
              <Icon name={module.icon as any} size={20} />
              <span className="font-medium flex-1 text-left">{module.name}</span>
              {locked && <Icon name="Lock" size={14} className="text-sidebar-foreground/60" />}
            </button>
          );
        })}
      </nav>

      <UserProfileMenu
        onOpenSettings={() => select('settings')}
        onOpenSubscription={() => select('subscription')}
        onOpenNotifications={() => select('notifications')}
      />
    </aside>
    </>
  );
};

export default AppSidebar;