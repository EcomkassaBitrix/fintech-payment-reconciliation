import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import Icon from '@/components/ui/icon';
import ScenarioStep from './ScenarioStep';
import {
  DEFAULT_DISCREPANCY_DELAY,
  DISCREPANCY_DELAY_OPTIONS,
  DISCREPANCY_KINDS,
  DiscrepancyKind,
  LOOKBACK_OPTIONS,
  VERIFY_MODES,
  VerifyMode
} from './automationConfig';

interface Props {
  mapping: Record<string, unknown>;
  onChange: (patch: Record<string, unknown>) => void;
  startStep: number;
}

const OptionCards = <T extends string>({
  options,
  value,
  onSelect,
  disabled
}: {
  options: { value: T; label: string; description: string }[];
  value: T;
  onSelect: (v: T) => void;
  disabled?: (v: T) => boolean;
}) => (
  <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
    {options.map((o) => {
      const off = disabled?.(o.value);
      return (
        <button
          key={o.value}
          type="button"
          disabled={off}
          onClick={() => onSelect(o.value)}
          className={`rounded-lg border-2 px-3 py-2.5 text-left transition-all disabled:cursor-not-allowed disabled:opacity-50 ${
            value === o.value ? 'border-primary bg-primary/5' : 'border-border hover:border-primary/50'
          }`}
        >
          <span className="block text-sm font-medium">{o.label}</span>
          <span className="mt-0.5 block text-xs text-muted-foreground">{o.description}</span>
        </button>
      );
    })}
  </div>
);

const ScenarioDiscrepancyFields = ({ mapping, onChange, startStep }: Props) => {
  const kind = (mapping.discrepancy_kind as DiscrepancyKind) || 'missing_receipt';
  const verify = (mapping.verify_mode as VerifyMode) || 'none';
  const delay = Number(mapping.delay_minutes) || DEFAULT_DISCREPANCY_DELAY;
  const lookback = mapping.lookback_days === 'year' ? 'year' : Number(mapping.lookback_days) || 3;
  const isInvoice = kind === 'pending_invoice';

  return (
    <>
      <ScenarioStep n={startStep} title="Что ищем">
        <OptionCards
          options={DISCREPANCY_KINDS}
          value={kind}
          onSelect={(v) =>
            onChange(v === 'pending_invoice' ? { discrepancy_kind: v, verify_mode: 'payment_system', lookback_days: lookback } : { discrepancy_kind: v })
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
        <OptionCards
          options={VERIFY_MODES}
          value={verify}
          onSelect={(v) => onChange({ verify_mode: v })}
          disabled={(v) => isInvoice && v === 'none'}
        />
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
