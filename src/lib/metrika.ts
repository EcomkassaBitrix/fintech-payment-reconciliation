// Электронная коммерция Яндекс Метрики (контейнер dataLayer): тарифы как товары.
export interface EcomTariff {
  slug: string;
  name: string;
  price: number;
}

const push = (event: string, products: Record<string, unknown>[], extra: Record<string, unknown> = {}) => {
  window.dataLayer = window.dataLayer || [];
  window.dataLayer.push({ ecommerce: { currencyCode: 'RUB', [event]: { ...extra, products } } });
};

const product = (t: EcomTariff, yearly: boolean, position?: number) => ({
  id: t.slug,
  name: t.name,
  price: t.price,
  category: 'Тарифы',
  variant: yearly ? 'Год' : 'Месяц',
  ...(position ? { position } : {})
});

export const ecomImpressions = (tariffs: EcomTariff[], yearly: boolean) =>
  push('impressions', tariffs.map((t, i) => ({ ...product(t, yearly, i + 1), list: 'Тарифы на сайте' })));

export const ecomDetail = (t: EcomTariff, yearly: boolean) => push('detail', [product(t, yearly)]);

export const ecomAdd = (t: EcomTariff, yearly: boolean) => push('add', [{ ...product(t, yearly), quantity: 1 }]);

export const ecomPurchase = (orderId: string, t: EcomTariff, yearly: boolean, revenue: number) =>
  push('purchase', [{ ...product(t, yearly), quantity: 1, price: revenue }], { actionField: { id: orderId, revenue } });

// Цели (JavaScript-события) Яндекс Метрики. Номер счётчика берётся из настроек платформы.
export const GOALS = {
  registration: 'registration',
  trialStarted: 'trial_started',
  tariffPaid: 'tariff_paid',
  promoActivated: 'promo_activated',
  integrationAdded: 'integration_added',
  scenarioAdded: 'scenario_added',
  userInvited: 'user_invited'
} as const;

export type GoalName = (typeof GOALS)[keyof typeof GOALS];

const pending: [GoalName, Record<string, unknown> | undefined][] = [];

export const setMetrikaCounter = (id: number) => {
  window.__ymCounterId = id;
  while (pending.length) {
    const [goal, params] = pending.shift()!;
    window.ym?.(id, 'reachGoal', goal, params);
  }
};

export const reachGoal = (goal: GoalName, params?: Record<string, unknown>) => {
  const id = window.__ymCounterId;
  if (id && window.ym) window.ym(id, 'reachGoal', goal, params);
  else pending.push([goal, params]);
};