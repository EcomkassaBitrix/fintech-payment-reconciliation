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

export interface CrmReference {
  fields: Record<'deal' | 'lead' | 'contact' | 'company', CrmField[]>;
  stages: { deal: CrmStage[]; lead: CrmStage[] };
}

export interface PlatformCrmSettings {
  webhook_url: string | null;
  is_enabled: boolean;
  entity: 'deal' | 'lead';
  stage_id: string | null;
  phone_field: string;
  phone_field_type: string | null;
  phone_to_contact: boolean;
  channel_field: string | null;
  channel_field_type: string | null;
  inn_field: string;
  inn_field_type: string | null;
  title_template: string;
}

export interface PlatformCrmEvent {
  id: number;
  kind: 'register' | 'profile' | 'company';
  status: 'new' | 'retry' | 'done' | 'failed';
  attempts: number;
  error: string | null;
  result: Record<string, unknown> | null;
  created_at: string;
  processed_at: string | null;
  phone: string | null;
  full_name: string | null;
  company_name: string | null;
  company_inn: string | null;
}

export const CRM_EVENT_KINDS: Record<string, string> = {
  register: 'Регистрация',
  profile: 'ФИО / почта',
  company: 'Компания'
};

export const CRM_EVENT_STATUSES: Record<string, { label: string; className: string }> = {
  new: { label: 'В очереди', className: 'bg-muted text-muted-foreground' },
  retry: { label: 'Повтор', className: 'bg-warning/10 text-warning border-warning/20' },
  done: { label: 'Передано', className: 'bg-success/10 text-success border-success/20' },
  failed: { label: 'Ошибка', className: 'bg-destructive/10 text-destructive border-destructive/20' }
};

const OBJECT_LABELS: Record<string, string> = { deal: 'Сделка', lead: 'Лид', contact: 'Контакт', company: 'Компания' };

export const fieldOptions = (ref: CrmReference | null, objects: ('deal' | 'lead' | 'contact' | 'company')[],
  accept?: (f: CrmField) => boolean) =>
  objects.flatMap((o) =>
    (ref?.fields[o] || [])
      .filter((f) => (accept ? accept(f) : true))
      .map((f) => ({ value: f.ref, label: `${OBJECT_LABELS[o]} · ${f.title}`, type: f.type }))
  );

export const describeResult = (e: PlatformCrmEvent) => {
  const r = (e.result || {}) as Record<string, string | boolean | undefined>;
  const parts: string[] = [];
  if (r.contact_id) parts.push(`контакт #${r.contact_id}${r.contact_found ? ' (найден по телефону)' : r.contact_created ? ' (новый)' : ''}`);
  if (r.entity_id) parts.push(`${r.entity === 'lead' ? 'лид' : 'сделка'} #${r.entity_id}`);
  if (r.company_id) parts.push(`компания #${r.company_id}${r.company_created ? ' (новая)' : ''}`);
  if (r.requisite && r.requisite !== 'ok') parts.push(`реквизит ИНН не сохранён: ${r.requisite}`);
  if (r.contact_name || r.contact_email) parts.push('контакт обновлён');
  return parts.join(', ');
};
