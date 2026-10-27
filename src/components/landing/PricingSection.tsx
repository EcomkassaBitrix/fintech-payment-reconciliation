import { useEffect, useState } from 'react';
import PaymentLogos from './PaymentLogos';
import { ecomAdd, ecomImpressions } from '@/lib/metrika';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import Icon from '@/components/ui/icon';
import { pluralDays } from '@/lib/trialDays';
import { discountedYearPrice, fullYearPrice, periodLabel } from '@/lib/tariffPricing';
import { rememberTariff } from '@/lib/chosenTariff';

export interface Tariff {
  slug: string;
  name: string;
  description: string;
  price: number;
  billing_period: string;
  max_companies: number | null;
  max_users: number | null;
  max_integrations: number | null;
  max_automations?: number | null;
  features: string[];
  period_days?: number;
  yearly_discount_percent?: number;
  trial_days?: number;
}

const FALLBACK_TARIFFS: Tariff[] = [
  {
    slug: 'trial',
    name: 'Пробный период',
    description: '7 дней бесплатно, все функции доступны',
    price: 0,
    billing_period: 'month',
    max_companies: 1,
    max_users: 3,
    max_integrations: 2,
    features: ['Все модули', 'Email поддержка']
  },
  {
    slug: 'start',
    name: 'Старт',
    description: 'Для небольшого бизнеса с одной компанией',
    price: 990,
    billing_period: 'month',
    max_companies: 1,
    max_users: 5,
    max_integrations: 3,
    features: ['Все модули', 'Приоритетная поддержка']
  },
  {
    slug: 'business',
    name: 'Бизнес',
    description: 'Для бухгалтерий и агентств с несколькими компаниями',
    price: 2990,
    billing_period: 'month',
    max_companies: 5,
    max_users: 20,
    max_integrations: 10,
    features: ['Все модули', 'Автоматизации', 'Приоритетная поддержка']
  }
];

interface PricingSectionProps {
  onCtaClick: () => void;
  trialDays: number;
  tariffs: Tariff[] | null;
  asPage?: boolean;
}

const PricingSection = ({ onCtaClick, trialDays, tariffs: loaded, asPage = false }: PricingSectionProps) => {
  const Heading = asPage ? 'h1' : 'h2';
  const tariffs = loaded ?? FALLBACK_TARIFFS;
  const trialLabel = pluralDays(trialDays);
  const [yearly, setYearly] = useState(false);
  // Максимальная скидка за год среди тарифов - для подписи на переключателе.
  const maxDiscount = Math.max(0, ...tariffs.filter((t) => t.price > 0).map((t) => t.yearly_discount_percent || 0));
  // Пробный период тарифа: своё поле, у тарифа «Пробный» без него - его срок действия.
  const trialOf = (t: Tariff) => (t.trial_days && t.trial_days > 0 ? t.trial_days : t.slug === 'trial' ? trialDays : 0);
  const fmt = (v: number) => `${Math.round(v).toLocaleString('ru-RU')} ₽`;

  // Электронная коммерция: показ тарифов (при загрузке и смене месяц/год).
  useEffect(() => {
    if (loaded) ecomImpressions(loaded, yearly);
  }, [loaded, yearly]);

  return (
    <section id="pricing" className="py-20 sm:py-28 bg-card/30">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="text-center max-w-2xl mx-auto mb-16">
          <Heading className="text-3xl sm:text-4xl font-display font-bold text-foreground mb-4">
            {asPage ? 'Тарифы и цены Сверки' : 'Простые и понятные тарифы'}
          </Heading>
          <p className="text-lg text-muted-foreground">
            Начните с бесплатного периода, растите — переключайтесь на тариф с бо́льшим числом функций для бизнеса.
          </p>
          <div className="mt-8 inline-flex items-center rounded-full border border-border bg-card p-1">
            {[false, true].map((isYear) => (
              <button
                key={String(isYear)}
                type="button"
                onClick={() => setYearly(isYear)}
                className={`flex items-center gap-2 rounded-full px-5 py-2 text-sm font-medium transition-colors ${
                  yearly === isYear ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                {isYear ? 'Год' : 'Месяц'}
                {isYear && maxDiscount > 0 && (
                  <span className={`rounded-full px-2 py-0.5 text-xs ${yearly ? 'bg-primary-foreground/20' : 'bg-success/15 text-success'}`}>
                    до −{maxDiscount}%
                  </span>
                )}
              </button>
            ))}
          </div>
        </div>

        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6 max-w-5xl mx-auto">
          {tariffs.map((tariff, index) => {
            const isPopular = tariff.slug === 'start';
            return (
              <Card
                key={tariff.slug}
                className={`relative border-border bg-card animate-fade-in ${isPopular ? 'border-primary shadow-lg shadow-primary/10' : ''}`}
                style={{ animationDelay: `${index * 0.05}s` }}
              >
                {isPopular && (
                  <div className="absolute -top-3 left-1/2 -translate-x-1/2 bg-primary text-primary-foreground text-xs font-semibold px-3 py-1 rounded-full">
                    Популярный
                  </div>
                )}
                <CardHeader>
                  <CardTitle className="text-xl font-display">{tariff.name}</CardTitle>
                  <CardDescription>
                    {tariff.slug === 'trial' || tariff.price === 0 ? `${pluralDays(trialOf(tariff) || trialDays)} бесплатно, все функции доступны` : tariff.description}
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="mb-6">
                    {tariff.price > 0 && yearly ? (
                      (() => {
                        const discount = tariff.yearly_discount_percent || 0;
                        const full = fullYearPrice(tariff.price, tariff.period_days);
                        const year = discountedYearPrice(tariff.price, tariff.period_days, discount);
                        return (
                          <>
                            <span className="text-4xl font-display font-bold text-foreground">{fmt(year)}</span>
                            <span className="text-muted-foreground text-sm"> / год</span>
                            <div className="mt-1 flex items-center gap-2 text-sm">
                              {discount > 0 && <span className="text-muted-foreground line-through">{fmt(full)}</span>}
                              <span className="text-muted-foreground">≈ {fmt(year / 12)} / мес</span>
                              {discount > 0 && <span className="font-medium text-success">−{discount}%</span>}
                            </div>
                          </>
                        );
                      })()
                    ) : (
                      <>
                        <span className="text-4xl font-display font-bold text-foreground">
                          {tariff.price > 0 ? fmt(tariff.price) : 'Бесплатно'}
                        </span>
                        {tariff.price > 0 && <span className="text-muted-foreground text-sm"> / {periodLabel(tariff.period_days)}</span>}
                      </>
                    )}
                    {tariff.price > 0 && trialOf(tariff) > 0 && (
                      <div className="mt-2 inline-flex items-center gap-1.5 rounded-full bg-success/15 px-2.5 py-0.5 text-xs font-medium text-success">
                        <Icon name="Gift" size={12} />
                        {pluralDays(trialOf(tariff))} бесплатно
                      </div>
                    )}
                  </div>

                  <ul className="space-y-3 mb-6">
                    <li className="flex items-center gap-2 text-sm text-muted-foreground">
                      <Icon name="Check" size={16} className="text-primary shrink-0" />
                      {tariff.max_companies == null ? 'Без ограничения компаний' : `До ${tariff.max_companies} ${tariff.max_companies === 1 ? 'компании' : 'компаний'}`}
                    </li>
                    <li className="flex items-center gap-2 text-sm text-muted-foreground">
                      <Icon name="Check" size={16} className="text-primary shrink-0" />
                      {tariff.max_users == null ? 'Без ограничения пользователей' : `До ${tariff.max_users} пользователей`}
                    </li>
                    <li className="flex items-center gap-2 text-sm text-muted-foreground">
                      <Icon name="Check" size={16} className="text-primary shrink-0" />
                      {tariff.max_integrations == null ? 'Без ограничения интеграций' : `До ${tariff.max_integrations} интеграций`}
                    </li>
                    {tariff.max_automations !== undefined && (
                      <li className="flex items-center gap-2 text-sm text-muted-foreground">
                        <Icon name="Check" size={16} className="text-primary shrink-0" />
                        {tariff.max_automations == null ? 'Без ограничения автоматизаций' : `До ${tariff.max_automations} ${tariff.max_automations === 1 ? 'автоматизации' : 'автоматизаций'}`}
                      </li>
                    )}
                    {tariff.features.map((feature) => (
                      <li key={feature} className="flex items-center gap-2 text-sm text-muted-foreground">
                        <Icon name="Check" size={16} className="text-primary shrink-0" />
                        {feature}
                      </li>
                    ))}
                  </ul>

                  <Button
                    className="w-full"
                    variant={isPopular ? 'default' : 'outline'}
                    onClick={() => {
                      ecomAdd(tariff, yearly);
                      rememberTariff(tariff.slug);
                      onCtaClick();
                    }}
                  >
                    {trialOf(tariff) > 0 ? `Попробовать ${pluralDays(trialOf(tariff))} бесплатно` : tariff.price > 0 ? 'Подключить' : `Попробовать ${trialLabel} бесплатно`}
                  </Button>
                </CardContent>
              </Card>
            );
          })}
        </div>
        <div className="mt-10 flex flex-col items-center gap-3 text-center text-sm text-muted-foreground">
          <PaymentLogos className="justify-center" />
          <p className="max-w-2xl">
            Цены в рублях. Онлайн‑сервис, доступ открывается сразу после оплаты картой «Мир», Visa, Mastercard или через
            T‑Pay на защищённой странице АО «ТБанк». Автопродление отключается в любой момент, деньги за
            неиспользованный период возвращаются по заявлению.{' '}
            <a href="/payment" className="text-primary hover:underline">
              Условия оплаты и возврата
            </a>
          </p>
        </div>
      </div>
    </section>
  );
};

export default PricingSection;