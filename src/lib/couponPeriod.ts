export type CouponPeriod = 'month' | 'quarter' | 'half_year' | 'year';

export const COUPON_PERIOD_LABELS: Record<CouponPeriod, string> = {
  month: '1 месяц',
  quarter: '3 месяца',
  half_year: '6 месяцев',
  year: '1 год',
};

export const couponPeriodLabel = (period: string) =>
  COUPON_PERIOD_LABELS[period as CouponPeriod] || '1 месяц';
