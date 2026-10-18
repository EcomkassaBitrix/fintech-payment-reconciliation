export interface ActionTemplateRow {
  id: number;
  code: string;
  action_type: 'create_receipt' | 'create_order';
  name: string;
  description: string | null;
  operation: string;
  paid: boolean;
  is_active: boolean;
  sort_order: number;
  provider_id: number | null;
  provider_name: string | null;
  protocol_version: string;
  receipt_type: string;
  payment_method: string;
  payment_object: string;
  measure: string;
  payment_type: number | null;
  default_email: string | null;
  correction_type: string | null;
  correction_date_source: string | null;
  correction_base_date: string | null;
  correction_base_number: string | null;
  correction_base_name: string | null;
  payment_address: string | null;
  vat: string | null;
  auto_deliver: boolean;
  cashier_name: string | null;
  agent_settings: Partial<AgentSettingsRow> | null;
  scenarios_count: number;
}

export interface ActionTemplateForm {
  code: string;
  action_type: 'create_receipt' | 'create_order';
  name: string;
  description: string;
  is_active: boolean;
  sort_order: number;
  provider_id: number | null;
  protocol_version: string;
  receipt_type: string;
  operation: string;
  payment_method: string;
  payment_object: string;
  measure: string;
  payment_type: string;
  default_email: string;
  correction_type: string;
  correction_date_source: string;
  correction_base_date: string;
  correction_base_number: string;
  correction_base_name: string;
  payment_address: string;
  vat: string;
  auto_deliver: boolean;
  cashier_name: string;
  agent_settings: AgentSettings;
}

export interface CashProvider {
  id: number;
  name: string;
}

export interface Option {
  value: string;
  label: string;
  hint?: string;
}

export const ACTION_TYPE_OPTIONS = [
  { value: 'create_receipt', label: 'Создать чек', icon: 'Receipt' },
  { value: 'create_order', label: 'Создать заказ', icon: 'Truck' }
] as const;

export const PROTOCOL_OPTIONS: Option[] = [
  { value: 'v4', label: 'v4', hint: 'ФФД 1.05' },
  { value: 'v5', label: 'v5', hint: 'ФФД 1.2' }
];

export const RECEIPT_TYPE_OPTIONS: Option[] = [
  { value: 'regular', label: 'Обычный' },
  { value: 'correction', label: 'Коррекция' },
  { value: 'agent', label: 'Агентский' }
];

// Агентский чек АТОЛ Онлайн. В форме телефоны - строкой через запятую.
export interface AgentSettings {
  agent_type: string;
  paying_agent_operation: string;
  paying_agent_phones: string;
  receive_payments_operator_phones: string;
  money_transfer_operator_name: string;
  money_transfer_operator_inn: string;
  money_transfer_operator_address: string;
  money_transfer_operator_phones: string;
  supplier_name: string;
  supplier_inn: string;
  supplier_phones: string;
}

type PhoneKey = 'paying_agent_phones' | 'receive_payments_operator_phones' | 'money_transfer_operator_phones' | 'supplier_phones';
export type AgentSettingsRow = Omit<AgentSettings, PhoneKey> & Record<PhoneKey, string[]>;
const PHONE_KEYS: PhoneKey[] = ['paying_agent_phones', 'receive_payments_operator_phones', 'money_transfer_operator_phones', 'supplier_phones'];

export const EMPTY_AGENT: AgentSettings = {
  agent_type: 'commission_agent',
  paying_agent_operation: '',
  paying_agent_phones: '',
  receive_payments_operator_phones: '',
  money_transfer_operator_name: '',
  money_transfer_operator_inn: '',
  money_transfer_operator_address: '',
  money_transfer_operator_phones: '',
  supplier_name: '',
  supplier_inn: '',
  supplier_phones: ''
};

// Теги 1057 (v4) / 1222 (v5) - признак агента, коды одинаковые.
export const AGENT_TYPE_OPTIONS: Option[] = [
  { value: 'commission_agent', label: 'Комиссионер', hint: 'commission_agent' },
  { value: 'attorney', label: 'Поверенный', hint: 'attorney' },
  { value: 'paying_agent', label: 'Платёжный агент', hint: 'paying_agent' },
  { value: 'paying_subagent', label: 'Платёжный субагент', hint: 'paying_subagent' },
  { value: 'bank_paying_agent', label: 'Банковский платёжный агент', hint: 'bank_paying_agent' },
  { value: 'bank_paying_subagent', label: 'Банковский платёжный субагент', hint: 'bank_paying_subagent' },
  { value: 'another', label: 'Другой агент', hint: 'another' }
];

export const isPayingAgent = (t: string) => ['paying_agent', 'paying_subagent', 'bank_paying_agent', 'bank_paying_subagent'].includes(t);
export const isBankAgent = (t: string) => ['bank_paying_agent', 'bank_paying_subagent'].includes(t);

const innOk = (v: string) => !v || /^(\d{10}|\d{12})$/.test(v);
// Маска телефона по ФФД: +7 и 10 цифр (+79999999999), несколько номеров - через запятую.
const maskPhone = (part: string) => {
  let d = part.replace(/\D/g, '');
  if (!d) return '';
  if (d[0] === '8') d = '7' + d.slice(1);
  else if (d[0] !== '7') d = '7' + d;
  return '+' + d.slice(0, 11);
};

export const maskPhones = (value: string) => {
  const parts = value.split(',');
  const masked = parts.slice(0, -1).map(maskPhone).filter(Boolean);
  const last = maskPhone(parts[parts.length - 1]);
  if (parts.length === 1) return last;
  return masked.join(', ') + (masked.length ? ',' : '') + (last ? ' ' + last : '');
};

export const phonesOk = (v: string) => v.split(',').every((p) => !p.trim() || /^\+7\d{10}$/.test(p.trim()));
export const PHONE_ERROR = 'Формат +79999999999, несколько — через запятую';

export const agentValid = (f: ActionTemplateForm) => {
  if (f.receipt_type !== 'agent') return true;
  const a = f.agent_settings;
  if (!a.agent_type) return false;
  if (!innOk(a.supplier_inn) || !innOk(a.money_transfer_operator_inn)) return false;
  if (!PHONE_KEYS.every((k) => phonesOk(a[k]))) return false;
  return true;
};

export const OPERATION_OPTIONS: Option[] = [
  { value: 'sell', label: 'Приход' },
  { value: 'sell_refund', label: 'Возврат прихода' }
];

// Тег 1214 АТОЛ Онлайн v4/v5.
export const PAYMENT_METHOD_OPTIONS: Option[] = [
  { value: 'full_prepayment', label: 'Предоплата 100%', hint: 'full_prepayment' },
  { value: 'prepayment', label: 'Предоплата', hint: 'prepayment' },
  { value: 'advance', label: 'Аванс', hint: 'advance' },
  { value: 'full_payment', label: 'Полный расчёт', hint: 'full_payment' },
  { value: 'partial_payment', label: 'Частичный расчёт и кредит', hint: 'partial_payment' },
  { value: 'credit', label: 'Передача в кредит', hint: 'credit' },
  { value: 'credit_payment', label: 'Оплата кредита', hint: 'credit_payment' }
];

// Тег 1212: v4 — строка, v5 — число.
export const PAYMENT_OBJECT_OPTIONS: Option[] = [
  { value: 'commodity', label: 'Товар', hint: 'v4 commodity · v5 1' },
  { value: 'commodity_marked', label: 'Маркированный товар', hint: 'v4 commodity · v5 33' },
  { value: 'service', label: 'Услуга', hint: 'v4 service · v5 4' },
  { value: 'job', label: 'Работа', hint: 'v4 job · v5 3' },
  { value: 'payment', label: 'Аванс', hint: 'v4 payment · v5 10' }
];

// v4 — measurement_unit (строка), v5 — measure (тег 2108).
export const MEASURE_OPTIONS: Option[] = [
  { value: 'piece', label: 'Штука', hint: 'v4 шт · v5 0' },
  { value: 'gram', label: 'Граммы', hint: 'v4 г · v5 10' },
  { value: 'kilogram', label: 'Килограммы', hint: 'v4 кг · v5 11' },
  { value: 'day', label: 'Сутки', hint: 'v4 сут · v5 70' }
];

// Ставка НДС для чека, когда у источника нет корзины (например, заказ Альфа-Банка без товаров).
export const VAT_IN_SCENARIO = 'scenario';
export const TEMPLATE_VAT_OPTIONS: Option[] = [
  { value: VAT_IN_SCENARIO, label: 'Задаётся в сценарии' },
  { value: 'none', label: 'Без НДС' },
  { value: 'vat0', label: 'НДС 0%' },
  { value: 'vat5', label: 'НДС 5%' },
  { value: 'vat7', label: 'НДС 7%' },
  { value: 'vat10', label: 'НДС 10%' },
  { value: 'vat20', label: 'НДС 20%' },
  { value: 'vat22', label: 'НДС 22%' },
  { value: 'vat105', label: 'НДС 5/105' },
  { value: 'vat107', label: 'НДС 7/107' },
  { value: 'vat110', label: 'НДС 10/110' },
  { value: 'vat120', label: 'НДС 20/120' },
  { value: 'vat122', label: 'НДС 22/122' }
];

export const NO_PAYMENT = 'none';

// payments[].type: пусто — документ без оплаты.
export const PAYMENT_TYPE_OPTIONS: Option[] = [
  { value: NO_PAYMENT, label: 'Пусто', hint: 'без оплаты' },
  { value: '0', label: 'Наличные', hint: 'type 0' },
  { value: '1', label: 'Безнал', hint: 'type 1' },
  { value: '2', label: 'Аванс', hint: 'type 2 · зачёт предоплаты' }
];

export const EMPTY_TEMPLATE: ActionTemplateForm = {
  code: '',
  action_type: 'create_order',
  name: '',
  description: '',
  is_active: true,
  sort_order: 100,
  provider_id: null,
  protocol_version: 'v4',
  receipt_type: 'regular',
  operation: 'sell',
  payment_method: 'full_payment',
  payment_object: 'commodity',
  measure: 'piece',
  payment_type: '1',
  default_email: '',
  correction_type: 'self',
  correction_date_source: 'payment',
  correction_base_date: '',
  correction_base_number: '',
  correction_base_name: '',
  payment_address: '',
  vat: VAT_IN_SCENARIO,
  auto_deliver: false,
  cashier_name: '',
  agent_settings: EMPTY_AGENT
};

export const DATE_SOURCE_OPTIONS: Option[] = [
  { value: 'payment', label: 'Дата платежа' },
  { value: 'today', label: 'Сегодня' },
  { value: 'fixed', label: 'Фиксированная дата' },
  { value: 'client', label: 'Заполнит клиент' }
];

// Только самостоятельная коррекция: номер и описание основания обязательны в v4.
// В шаблоне они необязательны - пустые клиент заполняет в своём сценарии.
export const needsBaseNumber = (f: Pick<ActionTemplateForm, 'protocol_version'>) => f.protocol_version === 'v4';

export const correctionValid = (f: ActionTemplateForm) =>
  f.receipt_type !== 'correction' ||
  ((f.correction_date_source !== 'fixed' || !!f.correction_base_date) && f.correction_base_number.trim().length <= 32);

export const labelOf = (options: Option[], value: string | null | undefined) =>
  options.find((o) => o.value === value)?.label || value || '—';

export const templateToForm = (t: ActionTemplateRow): ActionTemplateForm => ({
  code: t.code,
  action_type: t.action_type,
  name: t.name,
  description: t.description || '',
  is_active: t.is_active,
  sort_order: t.sort_order,
  provider_id: t.provider_id,
  protocol_version: t.protocol_version,
  receipt_type: t.receipt_type,
  operation: t.operation,
  payment_method: t.payment_method,
  payment_object: t.payment_object,
  measure: t.measure,
  payment_type: t.payment_type === null ? NO_PAYMENT : String(t.payment_type),
  default_email: t.default_email || '',
  correction_type: t.correction_type || 'self',
  correction_date_source: t.correction_date_source || 'payment',
  correction_base_date: t.correction_base_date ? t.correction_base_date.slice(0, 10) : '',
  correction_base_number: t.correction_base_number || '',
  correction_base_name: t.correction_base_name || '',
  payment_address: t.payment_address || '',
  vat: t.vat || VAT_IN_SCENARIO,
  auto_deliver: !!t.auto_deliver,
  cashier_name: t.cashier_name || '',
  agent_settings: agentToForm(t.agent_settings)
});

const agentToForm = (a: Partial<AgentSettingsRow> | null): AgentSettings => {
  const result: AgentSettings = { ...EMPTY_AGENT };
  if (!a) return result;
  (Object.keys(EMPTY_AGENT) as (keyof AgentSettings)[]).forEach((k) => {
    const v = a[k];
    if (Array.isArray(v)) result[k] = v.join(', ');
    else if (typeof v === 'string' && v) result[k] = v;
  });
  return result;
};

export const formToPayload = (f: ActionTemplateForm) => ({
  ...f,
  payment_type: f.payment_type === NO_PAYMENT ? null : Number(f.payment_type),
  default_email: f.default_email.trim() || null,
  vat: f.vat === VAT_IN_SCENARIO ? null : f.vat,
  agent_settings: f.receipt_type === 'agent' ? f.agent_settings : null
});
