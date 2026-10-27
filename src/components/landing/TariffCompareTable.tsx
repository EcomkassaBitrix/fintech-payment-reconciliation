import { Fragment, type ReactNode } from 'react';
import Icon from '@/components/ui/icon';
import { modules } from '@/components/access/accessTypes';
import { discountedYearPrice, periodLabel } from '@/lib/tariffPricing';
import { pluralDays } from '@/lib/trialDays';
import type { Tariff } from './PricingSection';

type TariffWithModules = Tariff & { modules?: string[] };

const fmt = (v: number) => `${Math.round(v).toLocaleString('ru-RU')} ₽`;
const yes = <Icon name="Check" size={18} className="mx-auto text-primary" />;
const no = <Icon name="Minus" size={18} className="mx-auto text-muted-foreground/50" />;
const limit = (v: number | null) => (v == null ? 'Без ограничений' : String(v));

interface Row {
  label: string;
  value: (t: TariffWithModules) => ReactNode;
}

const TariffCompareTable = ({ tariffs }: { tariffs: TariffWithModules[] }) => {
  const allFeatures = Array.from(
    new Set(tariffs.flatMap((t) => t.features).filter((f) => f !== 'Все модули'))
  );
  const hasModules = tariffs.some((t) => t.modules?.length);

  const groups: { title: string; rows: Row[] }[] = [
    {
      title: 'Стоимость',
      rows: [
        { label: 'Оплата помесячно', value: (t) => (t.price > 0 ? `${fmt(t.price)} / ${periodLabel(t.period_days)}` : 'Бесплатно') },
        {
          label: 'Оплата за год',
          value: (t) =>
            t.price > 0 ? fmt(discountedYearPrice(t.price, t.period_days, t.yearly_discount_percent || 0)) : '—'
        },
        { label: 'Скидка за год', value: (t) => (t.yearly_discount_percent ? `${t.yearly_discount_percent}%` : '—') },
        { label: 'Бесплатный период', value: (t) => (t.trial_days ? pluralDays(t.trial_days) : '—') }
      ]
    },
    {
      title: 'Лимиты',
      rows: [
        { label: 'Компаний', value: (t) => limit(t.max_companies) },
        { label: 'Пользователей', value: (t) => limit(t.max_users) },
        { label: 'Интеграций', value: (t) => limit(t.max_integrations) }
      ]
    },
    ...(hasModules
      ? [{
          title: 'Разделы сервиса',
          rows: modules.map((m) => ({ label: m.name, value: (t: TariffWithModules) => (t.modules?.includes(m.id) ? yes : no) }))
        }]
      : []),
    ...(allFeatures.length
      ? [{
          title: 'Поддержка и дополнительно',
          rows: allFeatures.map((f) => ({ label: f, value: (t: TariffWithModules) => (t.features.includes(f) ? yes : no) }))
        }]
      : [])
  ];

  return (
    <section className="pb-20 sm:pb-28 bg-card/30">
      <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8">
        <h2 className="text-2xl sm:text-3xl font-display font-bold text-foreground text-center mb-10">
          Сравнение тарифов
        </h2>
        <div className="overflow-x-auto rounded-xl border border-border bg-card">
          <table className="w-full min-w-[640px] text-sm">
            <thead>
              <tr className="border-b border-border">
                <th className="p-4 text-left font-medium text-muted-foreground w-1/3">Возможность</th>
                {tariffs.map((t) => (
                  <th
                    key={t.slug}
                    className={`p-4 text-center font-display font-bold text-base ${t.slug === 'start' ? 'text-primary' : 'text-foreground'}`}
                  >
                    {t.name}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {groups.map((g) => (
                <Fragment key={g.title}>
                  <tr className="bg-muted/40">
                    <td colSpan={tariffs.length + 1} className="px-4 py-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                      {g.title}
                    </td>
                  </tr>
                  {g.rows.map((r) => (
                    <tr key={r.label} className="border-t border-border">
                      <td className="p-4 text-foreground">{r.label}</td>
                      {tariffs.map((t) => (
                        <td key={t.slug} className={`p-4 text-center text-foreground ${t.slug === 'start' ? 'bg-primary/5' : ''}`}>
                          {r.value(t)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
};

export default TariffCompareTable;
