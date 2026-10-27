export interface AdminSection {
  id: string;
  name: string;
  icon: string;
}

export const ADMIN_SECTIONS: AdminSection[] = [
  { id: 'companies', name: 'Подписки', icon: 'CreditCard' },
  { id: 'support', name: 'Доступ ТП', icon: 'LifeBuoy' },
  { id: 'roles', name: 'Роли', icon: 'ShieldCheck' },
  { id: 'action_templates', name: 'Шаблоны действий', icon: 'Workflow' },
  { id: 'tariffs', name: 'Тарифы', icon: 'Tag' },
  { id: 'coupons', name: 'Купоны', icon: 'Ticket' },
  { id: 'payments', name: 'Оплата', icon: 'Wallet' },
  { id: 'integrations', name: 'Интеграции CRM', icon: 'Plug' },
  { id: 'banners', name: 'Баннеры', icon: 'Megaphone' },
  { id: 'cases', name: 'Кейсы', icon: 'BookOpenCheck' },
  { id: 'cron', name: 'Фоновые задачи', icon: 'Timer' },
  { id: 'settings', name: 'Настройки', icon: 'Settings' }
];