// Промокод из ссылки /promo/КОД: живёт до входа/регистрации и создания компании, затем применяется сам.
const KEY = 'pending_promo';
const TTL_MS = 7 * 24 * 60 * 60 * 1000;

export const rememberPromo = (code: string) => {
  try {
    localStorage.setItem(KEY, JSON.stringify({ code: code.trim().toUpperCase(), at: Date.now() }));
  } catch {
    /* хранилище недоступно - промокод можно ввести вручную */
  }
};

export const pendingPromo = (): string | null => {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return null;
    const { code, at } = JSON.parse(raw);
    return typeof code === 'string' && code && Date.now() - at < TTL_MS ? code : null;
  } catch {
    return null;
  }
};

export const forgetPromo = () => {
  try {
    localStorage.removeItem(KEY);
  } catch {
    /* ignore */
  }
};

export const promoLink = (code: string) => `${window.location.origin}/promo/${encodeURIComponent(code)}`;

export const SUBSCRIPTION_CHANGED = 'subscription-changed';
