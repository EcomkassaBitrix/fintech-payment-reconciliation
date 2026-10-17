export type TriggerType = 'new_payment' | 'crm_order' | 'discrepancy';
export type ActionType = 'create_receipt' | 'create_order';
export type ActionTemplate = string;
export type ScenarioStatus = 'active' | 'stopped';
export type JobStatus = 'new' | 'processing' | 'ready' | 'done' | 'skipped' | 'error' | 'failed';

export interface Scenario {
  id: number;
  name: string;
  trigger_type: TriggerType;
  source_integration_id: number | null;
  source_integration_name: string | null;
  action_type: ActionType;
  action_template: ActionTemplate;
  action_template_name?: string | null;
  target_integration_id: number | null;
  target_integration_name: string | null;
  field_mapping: Record<string, string>;
  correction_settings?: CorrectionSettings;
  status: ScenarioStatus;
  jobs_total: number;
  jobs_errors: number;
  last_job_at: string | null;
}

export interface AutomationJob {
  id: number;
  scenario_id: number;
  scenario_name: string;
  source_type: string;
  source_id: string;
  status: JobStatus;
  step: string;
  attempts: number;
  last_error: string | null;
  next_attempt_at: string | null;
  created_at: string;
}

export interface IntegrationOption {
  id: number;
  name: string;
  providerName: string;
  providerSlug?: string;
  category: string;
  stage?: string;
  webhookSettings?: Record<string, boolean>;
  protocolVersion?: string;
}

// sourceCategories: категории интеграций для выбора источника (null - внутренний источник)
export const TRIGGERS: Record<TriggerType, { label: string; icon: string; description: string; sourceCategories: string[] | null; needsMapping: boolean; actions?: ActionType[] }> = {
  new_payment: { label: 'Новый платёж', icon: 'CreditCard', description: 'Пришёл вебхук об оплате от эквайринга или платёж из «Мой Класс» / RealtyCalendar', sourceCategories: ['payments', 'moyklass', 'realtycalendar'], needsMapping: false },
  crm_order: { label: 'Заказ в CRM', icon: 'Users', description: 'Сделка или заказ в CRM перешли в нужную стадию', sourceCategories: ['crm'], needsMapping: true },
  discrepancy: { label: 'Расхождение', icon: 'TriangleAlert', description: 'Платёж без чека или зависший счёт — проверяем оплату и пробиваем чек (обычно коррекции)', sourceCategories: null, needsMapping: false, actions: ['create_receipt'] }
};

export const ACTIONS: Record<ActionType, { label: string; icon: string; description: string }> = {
  create_receipt: { label: 'Создать чек', icon: 'Receipt', description: 'Пробиваем чек в подключённой кассе по выбранному шаблону' },
  create_order: { label: 'Создать заказ', icon: 'Truck', description: 'Передаём заказ в службу доставки' }
};

// Шаблоны действий приходят из каталога платформы (админка → «Шаблоны действий»).
export interface ActionTemplateOption {
  code: string;
  name: string;
  action_type: ActionType;
  description: string | null;
  receipt_type?: string;
  protocol_version?: string;
  correction_base_number?: string | null;
  correction_base_name?: string | null;
  correction_date_source?: string | null;
  payment_address?: string | null;
  default_email?: string | null;
  vat?: string | null;
  auto_deliver?: boolean;
  cashier_name?: string | null;
  agent_settings?: Record<string, string | string[]> | null;
  payment_method?: string;
  payment_type?: number | null;
  operation?: string;
}

// Поля чека коррекции, которые задаются в сценарии (АТОЛ Онлайн):
// v4 (ФФД 1.05) - номер (1179) и описание (1177) основания обязательны;
// v5 (ФФД 1.2) - номер основания необязателен, описания нет. Место расчётов (1187) - в обеих.
export interface CorrectionSettings {
  correction_base_number?: string;
  correction_base_name?: string;
  payment_address?: string;
  default_email?: string;
  vat?: string;
  cashier_name?: string;
  // Агентские поля, не заданные в шаблоне. Телефоны - строкой через запятую (сервер хранит списком).
  agent?: Record<string, string | string[]>;
}

export const TARGET_CATEGORIES = ['cash_registers'];

// «Расхождение»: через сколько минут после оплаты считать, что чека нет.
export const DISCREPANCY_DELAY_OPTIONS = [
  { value: 5, label: '5 минут' },
  { value: 15, label: '15 минут' },
  { value: 30, label: '30 минут' },
  { value: 60, label: '1 час' },
  { value: 180, label: '3 часа' },
  { value: 720, label: '12 часов' },
  { value: 1440, label: '1 сутки' }
];
export const DEFAULT_DISCREPANCY_DELAY = 60;

export type DiscrepancyKind = 'missing_receipt' | 'pending_invoice';
export const DISCREPANCY_KINDS: { value: DiscrepancyKind; label: string; description: string }[] = [
  { value: 'missing_receipt', label: 'Оплачен, но нет чека', description: 'Платёж у нас оплачен, а ни чека кассы, ни чека ОФД нет' },
  { value: 'pending_invoice', label: 'Висит в ожидании оплаты', description: 'Счёт Екомкассы остаётся «ожидает оплату», хотя деньги могли прийти' }
];

// Проверка в банке скрыта до сверки эквайринга по дневной сумме зачисления.
export const BANK_VERIFY_ENABLED = false;
export type VerifyMode = 'none' | 'payment_system' | 'bank';
export const VERIFY_MODES: { value: VerifyMode; label: string; description: string }[] = [
  { value: 'none', label: 'Без проверки', description: 'Чек пробивается сразу, как нашли расхождение' },
  { value: 'payment_system', label: 'Проверка в платёжной системе', description: 'Спрашиваем статус у эквайринга — чек только если там «оплачен»' },
  { value: 'bank', label: 'Проверка в банке', description: 'Ищем поступление с номером платежа в выписке расчётного счёта' }
];

export const LOOKBACK_OPTIONS: { value: number | 'year'; label: string }[] = [
  { value: 1, label: '1 день' },
  { value: 3, label: '3 дня' },
  { value: 7, label: '7 дней' },
  { value: 14, label: '14 дней' },
  { value: 31, label: '31 день' },
  { value: 'year', label: 'этот год' }
];

// Сопоставление полей CRM для сценария «Заказ в CRM» (хранится в field_mapping сценария).
// Ссылка на поле - «объект.КОД»: deal.OPPORTUNITY, contact.EMAIL, company.UF_CRM_123.
export type CrmEntity = 'deal' | 'lead';
export type ItemsMode = 'products' | 'fixed' | 'single';

export interface FixedItem {
  name: string;
  price: string;
  quantity: string;
}

export const MAPPING_FIELDS: { key: string; label: string; required?: boolean; hint?: string }[] = [
  { key: 'order_id', label: 'Номер заказа', required: true },
  { key: 'amount', label: 'Сумма', hint: 'Для сверки с суммой товаров' },
  { key: 'customer_email', label: 'Email покупателя' },
  { key: 'customer_phone', label: 'Телефон покупателя' },
  { key: 'customer_name', label: 'Покупатель (имя / название)' },
  { key: 'customer_inn', label: 'ИНН покупателя' }
];

// Поставщик агентского чека из полей CRM (наименование, ИНН, телефоны).
export const AGENT_MAPPING_FIELDS: { key: string; label: string; agentKey: string }[] = [
  { key: 'agent_supplier_name', label: 'Наименование поставщика', agentKey: 'supplier_name' },
  { key: 'agent_supplier_inn', label: 'ИНН поставщика', agentKey: 'supplier_inn' },
  { key: 'agent_supplier_phones', label: 'Телефоны поставщика', agentKey: 'supplier_phones' }
];

export const DEFAULT_CRM_MAPPING: Record<string, unknown> = {
  entity: 'deal',
  pipeline: '',
  stage: '',
  order_id: 'deal.ID',
  amount: 'deal.OPPORTUNITY',
  customer_email: 'contact.EMAIL',
  customer_phone: 'contact.PHONE',
  customer_name: '',
  customer_inn: '',
  items_mode: 'products',
  fixed_items: [],
  single_item_name: 'Оплата по сделке №{ID}',
  vat: 'auto'
};

export const ENTITY_LABELS: Record<string, string> = {
  deal: 'Сделка', lead: 'Лид', contact: 'Контакт', company: 'Компания',
  booking: 'Бронь', client: 'Гость', apartment: 'Объект',
  payment: 'Платёж', user: 'Ученик', subscription: 'Абонемент', sub_type: 'Вид абонемента', group: 'Группа', course: 'Программа'
};

// «Мой Класс»: сопоставление полей для сценария «Новый платёж» (платёж или списание).
export const MOYKLASS_ENTITIES = ['payment', 'user', 'subscription', 'sub_type', 'group', 'course'];
export const MOYKLASS_ITEMS_MODES: { value: ItemsMode; label: string; description: string }[] = [
  { value: 'single', label: 'Одной позицией', description: 'Одна строка: название и сумма — из полей «Мой Класс» (можно формулой)' },
  { value: 'fixed', label: 'Фиксированный', description: 'Всегда один и тот же состав чека' }
];
export const RK_ENTITIES = ['booking', 'client', 'apartment', 'payment'];
export const realtycalendarDefaultMapping = (): Record<string, unknown> => ({
  order_id: 'booking.id',
  amount: 'payment.amount',
  customer_email: 'client.email',
  customer_phone: 'client.phone',
  customer_name: 'client.fio',
  customer_inn: '',
  items_mode: 'single',
  fixed_items: [],
  single_item_name: 'Проживание «{apartment.title}» с {booking.begin_date} по {booking.end_date}',
  single_item_amount: '',
  vat: 'none'
});

export const moyklassDefaultMapping = (offset: boolean): Record<string, unknown> => ({
  order_id: 'payment.id',
  amount: 'payment.summa',
  customer_email: 'user.email',
  customer_phone: 'user.phone',
  customer_name: 'user.name',
  customer_inn: '',
  items_mode: 'single',
  fixed_items: [],
  single_item_name: offset ? 'Занятие по абонементу «{sub_type.name}»' : 'Абонемент «{sub_type.name}»',
  single_item_amount: '',
  vat: 'none'
});

export const ITEMS_MODES: { value: ItemsMode; label: string; description: string }[] = [
  { value: 'products', label: 'Товары из CRM', description: 'Берём товарные строки сделки как есть' },
  { value: 'fixed', label: 'Фиксированный', description: 'Всегда один и тот же состав чека' },
  { value: 'single', label: 'Одной позицией', description: 'Одна строка на сумму из поля «Сумма»' }
];

export const VAT_OPTIONS = [
  { value: 'auto', label: 'Как в CRM' },
  { value: 'none', label: 'Без НДС' },
  { value: 'vat0', label: 'НДС 0%' },
  { value: 'vat5', label: 'НДС 5%' },
  { value: 'vat7', label: 'НДС 7%' },
  { value: 'vat10', label: 'НДС 10%' },
  { value: 'vat20', label: 'НДС 20%' },
  { value: 'vat22', label: 'НДС 22%' }
];

const TEMPLATE_VAT_LABELS: Record<string, string> = {
  none: 'Без НДС', vat0: 'НДС 0%', vat5: 'НДС 5%', vat7: 'НДС 7%', vat10: 'НДС 10%', vat20: 'НДС 20%', vat22: 'НДС 22%',
  vat105: 'НДС 5/105', vat107: 'НДС 7/107', vat110: 'НДС 10/110', vat120: 'НДС 20/120', vat122: 'НДС 22/122'
};
export const templateVatLabel = (vat?: string | null) => (vat ? TEMPLATE_VAT_LABELS[vat] || vat : '');

export interface CrmField {
  ref: string;
  code: string;
  title: string;
  type: string;
  multiple: boolean;
  custom: boolean;
  items?: { value: string; label: string }[];
}

export interface CrmStage {
  value: string;
  label: string;
  group?: string;
  group_id?: string;
}

export interface CrmMeta {
  fields: Record<string, CrmField[]>;
  stages: Record<CrmEntity, CrmStage[]>;
}

export const JOB_STATUS: Record<JobStatus, { label: string; className: string }> = {
  new: { label: 'В очереди', className: 'bg-muted text-muted-foreground border-border' },
  processing: { label: 'В работе', className: 'bg-info/15 text-info border-info/30' },
  ready: { label: 'Данные собраны', className: 'bg-info/15 text-info border-info/30' },
  done: { label: 'Выполнено', className: 'bg-success/15 text-success border-success/30' },
  skipped: { label: 'Пропущен', className: 'bg-muted text-muted-foreground border-border' },
  error: { label: 'Ошибка, повтор', className: 'bg-warning/15 text-warning border-warning/30' },
  failed: { label: 'Не удалось', className: 'bg-destructive/15 text-destructive border-destructive/30' }
};

// Группы шаблонов чеков в выпадающем списке сценария (только для удобства выбора).
export const TEMPLATE_GROUPS = [
  { key: 'sale', label: 'Продажа' },
  { key: 'refund', label: 'Возврат' },
  { key: 'advance', label: 'Аванс и предоплата' },
  { key: 'agent', label: 'Агентские' },
  { key: 'correction', label: 'Коррекция' },
  { key: 'other', label: 'Другие' }
] as const;

export const templateGroup = (t: ActionTemplateOption): string => {
  if (t.action_type !== 'create_receipt') return 'other';
  if (t.receipt_type === 'correction') return 'correction';
  if (t.receipt_type === 'agent') return 'agent';
  const prepay = !!t.payment_method && t.payment_method !== 'full_payment';
  if (prepay || t.payment_type === 2) return 'advance';
  if (t.operation === 'sell_refund') return 'refund';
  if (t.operation === 'sell' || !t.operation) return 'sale';
  return 'other';
};
