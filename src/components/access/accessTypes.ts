export interface CompanyUser {
  id: number;
  full_name: string | null;
  email: string | null;
  phone: string;
  role_slug: string;
  role_name: string;
  role_color: string;
  status: 'active' | 'pending' | 'blocked' | 'removed';
  invited_at: string | null;
  joined_at: string | null;
}

export interface Invite {
  id: number;
  phone: string;
  email: string | null;
  full_name: string | null;
  channel: string;
  role_slug: string;
  role_name: string;
  role_color: string;
  created_at: string | null;
  expires_at: string | null;
}

export interface Role {
  id: number;
  slug: string;
  name: string;
  description: string;
  color: string;
  modules: string[];
  permissions: string[];
  is_system: boolean;
}

export interface NewUserForm {
  phone: string;
  fullName: string;
  email: string;
  role: string;
  messenger: 'telegram' | 'whatsapp' | 'max' | 'email';
}

export const modules = [
  { id: 'reconciliation', name: 'Сверка', icon: 'GitCompare' },
  { id: 'events', name: 'События', icon: 'Radio' },
  { id: 'transactions', name: 'Транзакции', icon: 'ArrowLeftRight' },
  { id: 'automation', name: 'Автоматизация', icon: 'Workflow' },
  { id: 'integrations', name: 'Интеграции', icon: 'Plug' },
  { id: 'access', name: 'Управление доступом', icon: 'Users' },
  { id: 'settings', name: 'Настройки', icon: 'Settings' }
];

export const channelProviderMap: Record<string, string> = {
  whatsapp: 'ek_wa',
  telegram: 'ek_tg',
  max: 'ek_max',
  email: 'ek_email'
};

export const channelLabelMap: Record<string, string> = {
  whatsapp: 'WhatsApp',
  telegram: 'Telegram',
  max: 'Max',
  email: 'почту'
};
