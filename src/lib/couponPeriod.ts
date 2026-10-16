export type CouponPeriod = 'month' | 'quarter' | 'half_year' | 'year';

export const COUPON_PERIOD_LABELS: Record<CouponPeriod, string> = {
  month: '1 месяц',
  quarter: '3 месяца',
  half_year: '6 месяцев',
  year: '1 год',
};

export const couponPeriodLabel = (period: string) =>
  COUPON_PERIOD_LABELS[period as CouponPeriod] || '1 месяц';

const CODE_ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';

export const randomCode = () => {
  const bytes = new Uint8Array(8);
  crypto.getRandomValues(bytes);
  const chars = Array.from(bytes, (b) => CODE_ALPHABET[b % CODE_ALPHABET.length]).join('');
  return `${chars.slice(0, 4)}-${chars.slice(4)}`;
};
