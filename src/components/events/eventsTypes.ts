export interface EventWebhookHistoryItem {
  id: number;
  status: string | null;
  error_message: string | null;
  created_at: string | null;
  raw: any;
  event_type: string | null;
}

export type EventTransactionType = 'payment' | 'receipt' | 'receipt_order' | 'money' | 'crm';

export interface AppEvent {
  id: string;
  source: 'payment' | 'crm' | 'bank_statement';
  created_at: string | null;
  provider_slug: string;
  provider_type: string;
  transaction_type: EventTransactionType;
  payment_provider?: string | null;
  integration_name: string;
  event_type: string | null;
  status: string | null;
  error_message: string | null;
  event_number: string | null;
  summary: string;
  raw: any;
  webhook_history?: EventWebhookHistoryItem[];
  origin?: EventOrigin | null;
  receipt_kind?: string | null;
}
export type EventSource = 'acquiring' | 'kassa' | 'ofd' | 'bank' | 'crm';

export const EVENT_SOURCE_OPTIONS: { value: EventSource; label: string; icon: string }[] = [
  { value: 'acquiring', label: 'Эквайринг', icon: 'CreditCard' },
  { value: 'kassa', label: 'Касса', icon: 'Receipt' },
  { value: 'ofd', label: 'ОФД', icon: 'FileCheck' },
  { value: 'bank', label: 'Банк', icon: 'Landmark' },
  { value: 'crm', label: 'CRM', icon: 'Users' }
];

export type EventOrigin = 'webhook' | 'cron' | 'recovery' | 'candidate' | 'manual' | 'sync' | 'automation';

export const EVENT_ORIGIN_LABELS: Record<EventOrigin, { label: string; hint: string; icon: string }> = {
  webhook: { label: 'Вебхук', hint: 'Уведомление пришло от сервиса', icon: 'Webhook' },
  cron: { label: 'Крон', hint: 'Загружено планировщиком', icon: 'Clock' },
  recovery: { label: 'Крон (вместо хука)', hint: 'Хук не пришёл - планировщик нашёл и подтянул сам', icon: 'RefreshCw' },
  candidate: { label: 'Крон (кандидат)', hint: 'Найдена по сумме и времени оплаты - связь подтверждает человек', icon: 'SearchCheck' },
  manual: { label: 'Ручная загрузка', hint: 'Загружено вручную из кабинета', icon: 'Hand' },
  sync: { label: 'Дозагрузка', hint: 'Подтянуто при синхронизации данных', icon: 'RefreshCw' },
  automation: { label: 'Автоматизация', hint: 'Создано сценарием автоматизации', icon: 'Workflow' },
};
