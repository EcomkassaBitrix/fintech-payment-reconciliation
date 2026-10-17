import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import Icon from '@/components/ui/icon';
import ScenarioStep from './ScenarioStep';
import OptionList from './OptionList';
import {
  DEFAULT_DISCREPANCY_DELAY,
  DISCREPANCY_DELAY_OPTIONS,
  DISCREPANCY_KINDS,
  DiscrepancyKind,
  LOOKBACK_OPTIONS,
  VERIFY_MODES,
  VerifyMode,
  BANK_VERIFY_ENABLED
} from './automationConfig';

interface Props {
  mapping: Record<string, unknown>;
  onChange: (patch: Record<string, unknown>) => void;
  startStep: number;
  hasPayments: boolean;
  hasBanks: boolean;
}

const ScenarioDiscrepancyFields = ({ mapping, onChange, startStep, hasPayments, hasBanks }: Props) => {
  const kind = (mapping.discrepancy_kind as DiscrepancyKind) || 'missing_receipt';
  const verify = (mapping.verify_mode as VerifyMode) || 'none';
  const delay = Number(mapping.delay_minutes) || DEFAULT_DISCREPANCY_DELAY;
  const lookback = mapping.lookback_days === 'year' ? 'year' : Number(mapping.lookback_days) || 3;
  const isInvoice = kind === 'pending_invoice';

  return (
    <>
      <ScenarioStep n={startStep} title="Что ищем">
        <OptionList
          options={DISCREPANCY_KINDS}
          value={kind}
          onSelect={(v) =>
            onChange(
              v === 'pending_invoice'
                ? { discrepancy_kind: v, verify_mode: 'payment_system', lookback_days: lookback }
                : { discrepancy_kind: v }
            )
          }
        />
      </ScenarioStep>

      <ScenarioStep n={startStep + 1} title="Когда считать, что чека нет">
        <Select value={String(delay)} onValueChange={(v) => onChange({ delay_minutes: Number(v) })}>
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {DISCREPANCY_DELAY_OPTIONS.map((o) => (
              <SelectItem key={o.value} value={String(o.value)}>
                Через {o.label} {isInvoice ? 'после создания счёта' : 'после оплаты'}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {isInvoice ? (
          <div className="space-y-2">
            <Select value={String(lookback)} onValueChange={(v) => onChange({ lookback_days: v === 'year' ? 'year' : Number(v) })}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {LOOKBACK_OPTIONS.map((o) => (
                  <SelectItem key={o.value} value={String(o.value)}>
                    {o.value === 'year' ? 'Смотреть счета за этот год' : `Смотреть счета за ${o.label}`}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">
              Берём счета Екомкассы в статусе «ожидает оплату» за выбранный период. Неоплаченные счета за последние 3 дня перепроверяем раз в 6 часов, более старые — проверяем один раз.
            </p>
          </div>
        ) : (
          <p className="text-xs text-muted-foreground">
            Проверяются оплаченные платежи всех платёжек компании. Если за это время не пришёл ни чек кассы, ни чек ОФД —
            пробиваем чек по корзине платежа. Нет корзины — чек не пробиваем, задание останавливается с ошибкой.
          </p>
        )}
      </ScenarioStep>

      <ScenarioStep n={startStep + 2} title="Проверка">
        <OptionList
          options={VERIFY_MODES.filter((m) => m.value !== 'bank' || (BANK_VERIFY_ENABLED && hasBanks))}
          value={verify}
          onSelect={(v) => onChange({ verify_mode: v })}
          disabled={(v) =>
            v === 'none'
              ? isInvoice && 'Для зависших счетов нужна проверка'
              : v === 'payment_system'
                ? !hasPayments && 'Подключите платёжную систему в разделе «Платежи»'
                : !hasBanks && 'Подключите расчётный счёт в разделе «Банки»'
          }
        />
        {verify === 'bank' && (
          <div className="flex gap-2 rounded-lg border border-border bg-muted/40 p-3 text-xs text-muted-foreground">
            <Icon name="Landmark" size={16} className="mt-0.5 shrink-0 text-primary" />
            <div className="space-y-1">
              <p>
                Ищем в выписках подключённых расчётных счетов входящее поступление, в назначении которого есть {isInvoice ? 'номер счёта Екомкассы' : 'номер платежа или заказа'}, или зачисление, уже привязанное к платежу в сверке.
              </p>
              <p>Нашли — пробиваем чек. Не нашли — чек не пробиваем. Выписка обновляется по расписанию банка, поэтому свежих поступлений в ней может ещё не быть.</p>
            </div>
          </div>
        )}
        {verify === 'payment_system' && (
          <div className="flex gap-2 rounded-lg border border-border bg-muted/40 p-3 text-xs text-muted-foreground">
            <Icon name="ShieldCheck" size={16} className="mt-0.5 shrink-0 text-primary" />
            <div className="space-y-1">
              {isInvoice ? (
                <p>Номер счёта Екомкассы ищем как номер заказа в подключённом эквайринге Т-Банка или Альфа-Банка.</p>
              ) : (
                <p>Статус спрашиваем у платёжки, откуда пришёл платёж: Т-Банк, Альфа-Банк, шлюз Екомкассы (через Т-Банк / Альфа-Банк).</p>
              )}
              <p>«Оплачен» — пробиваем чек и отмечаем платёж оплаченным. Не оплачен или отменён — чек не нужен. Банк не ответил — повторим позже.</p>
            </div>
          </div>
        )}
      </ScenarioStep>
    </>
  );
};

export default ScenarioDiscrepancyFields;
