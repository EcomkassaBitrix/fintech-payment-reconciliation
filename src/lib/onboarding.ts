const KEY = 'ek_onboarding';

type Store = Record<string, number>;

const read = (): Store => {
  try {
    return JSON.parse(localStorage.getItem(KEY) || '{}') || {};
  } catch {
    return {};
  }
};

const write = (store: Store) => localStorage.setItem(KEY, JSON.stringify(store));

export const ONBOARDING_STEPS = 5;

export const ONBOARDING_EVENT = 'ek-onboarding-start';

export const startOnboarding = (companyId: number) => {
  write({ ...read(), [companyId]: 0 });
  window.dispatchEvent(new Event(ONBOARDING_EVENT));
};

export const onboardingStep = (companyId?: number | null): number | null => {
  if (!companyId) return null;
  const step = read()[companyId];
  return typeof step === 'number' ? step : null;
};

export const saveOnboardingStep = (companyId: number, step: number) => write({ ...read(), [companyId]: step });

export const finishOnboarding = (companyId: number) => {
  const store = read();
  delete store[companyId];
  write(store);
};
