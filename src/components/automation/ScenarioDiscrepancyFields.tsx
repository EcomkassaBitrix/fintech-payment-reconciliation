import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import ScenarioStep from './ScenarioStep';
import OptionList from './OptionList';
import { Checkbox } from '@/components/ui/checkbox';
import {
  DEFAULT_DISCREPANCY_DELAY,
  DISCREPANCY_DELAY_OPTIONS,
  DISCREPANCY_KINDS,
  DiscrepancyKind,
  IntegrationOption,
  ORDER_CHECK_PROVIDERS
} from './automationConfig';

interface Props {
  mapping: Record<string, unknown>;
  onChange: (patch: Record<string, unknown>) => void;
  startStep: number;
  paymentSystems: IntegrationOption[];
}

const ScenarioDiscrepancyFields = ({ mapping, onChange, startStep, paymentSystems }: Props) => {
  const kind = (mapping.discrepancy_kind as DiscrepancyKind) || 'missing_receipt';
  const checkIds = Array.isArray(mapping.verify_integration_ids) ? (mapping.verify_integration_ids as number[]) : [];
  const verifyIds = mapping.verify_mode === 'payment_system' ? checkIds : [];
  const toggleSystem = (id: number) => {
    const next = verifyIds.includes(id) ? verifyIds.filter((x) => x !== id) : [...verifyIds, id];
    onChange(next.length ? { verify_mode: 'payment_system', verify_integration_ids: next } : { verify_mode: 'none', verify_integration_ids: [] });
  };
  const delay = Number(mapping.delay_minutes) || DEFAULT_DISCREPANCY_DELAY;
  const isInvoice = kind === 'pending_invoice';

  return (
    <>
      <ScenarioStep n={startStep} title="Что ищем">
        <OptionList
          options={DISCREPANCY_KINDS}
          value={kind}
          onSelect={(v) =>
            onChange({ discrepancy_kind: v, verify_mode: 'none', verify_integration_ids: [] })
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
          <p className="text-xs text-muted-foreground">
            Берём счета Екомкассы «ожидает оплату», загруженные вручную в «Событиях» (кнопка «Загрузить» → Платежи →
            Ожидает оплату). Неоплаченные счета за последние 3 дня перепроверяем раз в 6 часов, более старые — проверяем один раз.
          </p>
        ) : (
          <p className="text-xs text-muted-foreground">
            Проверяются оплаченные платежи всех платёжек компании. Если за это время не пришёл ни чек кассы, ни чек ОФД —
            пробиваем чек по корзине платежа. Нет корзины — чек не пробиваем, задание останавливается с ошибкой.
          </p>
        )}
      </ScenarioStep>

      {isInvoice && (
        <ScenarioStep n={startStep + 2} title="Проверка оплаты">
          <div className="divide-y divide-border overflow-hidden rounded-lg border border-border">
            <button
              type="button"
              onClick={() => onChange({ verify_mode: 'none', verify_integration_ids: [] })}
              className={`flex w-full items-start gap-3 px-3 py-2.5 text-left transition-colors ${verifyIds.length === 0 ? 'bg-primary/5' : 'hover:bg-muted/50'}`}
            >
              <Checkbox checked={verifyIds.length === 0} className="mt-0.5 pointer-events-none" />
              <span className="min-w-0">
                <span className="block text-sm font-medium">Без проверки</span>
                <span className="mt-0.5 block text-xs text-muted-foreground">Считаем счёт оплаченным и пробиваем чек коррекции сразу</span>
              </span>
            </button>
            {paymentSystems.map((ps) => {
              const supported = !!ps.providerSlug && ORDER_CHECK_PROVIDERS.includes(ps.providerSlug);
              const on = verifyIds.includes(ps.id);
              return (
                <button
                  key={ps.id}
                  type="button"
                  disabled={!supported}
                  onClick={() => toggleSystem(ps.id)}
                  className={`flex w-full items-start gap-3 px-3 py-2.5 text-left transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${on ? 'bg-primary/5' : 'hover:bg-muted/50'}`}
                >
                  <Checkbox checked={on} disabled={!supported} className="mt-0.5 pointer-events-none" />
                  <span className="min-w-0">
                    <span className="block text-sm font-medium">Проверка в «{ps.name}»</span>
                    <span className="mt-0.5 block text-xs text-muted-foreground">
                      {supported
                        ? `${ps.providerName}: ищем номер счёта Екомкассы как номер заказа, чек — только если «оплачен»`
                        : `${ps.providerName}: проверка по номеру заказа пока не поддерживается`}
                    </span>
                  </span>
                </button>
              );
            })}
          </div>
          {paymentSystems.length === 0 && (
            <p className="text-xs text-muted-foreground">Чтобы проверять оплату, подключите эквайринг в разделе «Платежи».</p>
          )}
          {verifyIds.length > 0 && (
            <p className="text-xs text-muted-foreground">
              Оплачен хотя бы в одной из отмеченных — пробиваем чек и отмечаем платёж оплаченным. Не оплачен — чек не нужен. Банк не ответил — повторим позже.
            </p>
          )}
        </ScenarioStep>
      )}
    </>
  );
};

export default ScenarioDiscrepancyFields;
