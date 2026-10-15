export interface PlanTariff {
  slug: string;
  name: string;
  description?: string;
  price: number;
  period_days: number;
  yearly_discount_percent: number;
  year_price: number;
  modules: string[];
  max_companies: number | null;
  max_users: number | null;
  max_integrations: number | null;
  max_automations: number | null;
}

export interface Payment {
  id: number;
  tariff_name: string;
  period: string;
  amount: number;
  period_end: string | null;
  created_at: string;
  method?: string;
  status?: string;
  is_recurring?: boolean;
  error?: string | null;
  days?: number;
  paid_at?: string | null;
  refund_amount?: number | null;
  refunded_at?: string | null;
  payment_url?: string | null;
  coupon_code?: string | null;
}

export interface AutoPay {
  auto_renew: boolean;
  period: string;
  card: { pan: string; exp_date: string | null; provider?: string } | null;
}

export const PAYMENT_METHODS: Record<string, { label: string; icon: string }> = {
  platform: { label: 'Начислено платформой', icon: 'Gift' },
  coupon: { label: 'Промокод', icon: 'Ticket' },
  manual: { label: 'Оплата без платёжной системы', icon: 'CreditCard' },
  tbank: { label: 'Картой через Т‑Банк', icon: 'CreditCard' },
  tochka: { label: 'Точка', icon: 'CreditCard' }
};

export type Period = 'month' | 'year';

export interface CurrentPlan {
  modules: string[];
  max_companies: number | null;
  max_users: number | null;
  max_integrations: number | null;
  max_automations: number | null;
}

export type LimitKey = 'max_companies' | 'max_users' | 'max_integrations' | 'max_automations';

export const LIMITS: { key: LimitKey; label: string }[] = [
  { key: 'max_companies', label: 'Компаний' },
  { key: 'max_users', label: 'Пользователей' },
  { key: 'max_integrations', label: 'Интеграций' },
  { key: 'max_automations', label: 'Автоматизаций' }
];

export const money = (n: number) => `${new Intl.NumberFormat('ru-RU').format(n)} ₽`;

// Изменение лимита относительно текущего тарифа: null в лимите - без ограничений.
export const limitDiff = (next: number | null, cur: number | null | undefined): { up: boolean; text: string } | null => {
  if (cur === undefined) return null;
  if (cur === null && next === null) return null;
  if (next === null) return { up: true, text: '' };
  if (cur === null) return { up: false, text: '' };
  if (next === cur) return null;
  return next > cur ? { up: true, text: `+${next - cur}` } : { up: false, text: `−${cur - next}` };
};
