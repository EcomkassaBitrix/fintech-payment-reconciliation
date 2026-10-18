import functionUrls from '../../../../backend/func2url.json';

export interface NamedIntegration {
  id: number;
  name: string;
}

export interface ActiveSources {
  ecomkassa: NamedIntegration[];
  ofd: NamedIntegration[];
  bank: NamedIntegration[];
}

export type DocType = 'payments' | 'receipts' | 'money' | 'orders';
export type SourceKind = 'ecomkassa' | 'ofd' | 'bank';

// Статус документа в окне загрузки -> коды статусов Екомкассы (для ОФД и банков
// статус один и служит подписью).
export interface StatusOption {
  id: string;
  label: string;
  codes: string[];
}

interface CategorySource {
  kind: SourceKind;
  orderType?: string;
  statuses: StatusOption[];
}

export interface DocCategory {
  id: DocType;
  label: string;
  icon: string;
  sources: CategorySource[];
}

// Категория -> интеграции -> статусы документов.
// - Платежи: счета Екомкассы (INVC - счёт с оплатой через шлюз = факт платежа);
// - Чеки: чеки Екомкассы (VCHR) + чеки ОФД;
// - Деньги: выписка по расчётным счетам банков;
// - Заказы: курьерские заказы Екомкассы (CORD).
export const DOC_CATEGORIES: DocCategory[] = [
  {
    id: 'payments', label: 'Платежи', icon: 'CreditCard',
    sources: [{ kind: 'ecomkassa', orderType: 'INVC', statuses: [{ id: 'paid', label: 'Оплачено', codes: ['PAID', 'COMPLETED'] }] }]
  },
  {
    id: 'receipts', label: 'Чеки', icon: 'Receipt',
    sources: [
      { kind: 'ecomkassa', orderType: 'VCHR', statuses: [{ id: 'completed', label: 'Завершён', codes: ['COMPLETED'] }] },
      { kind: 'ofd', statuses: [{ id: 'sent', label: 'Отправлен в ФНС', codes: [] }] }
    ]
  },
  {
    id: 'money', label: 'Деньги', icon: 'Landmark',
    sources: [{ kind: 'bank', statuses: [{ id: 'done', label: 'Проведено', codes: [] }] }]
  },
  {
    id: 'orders', label: 'Заказы', icon: 'Truck',
    sources: [{ kind: 'ecomkassa', orderType: 'CORD', statuses: [{ id: 'completed', label: 'Завершён', codes: ['COMPLETED'] }] }]
  }
];

// Одна строка-интеграция внутри категории.
export interface SourceItem {
  key: string;
  kind: SourceKind;
  name: string;
  orderType?: string;
  integrationId?: number;
  statuses: StatusOption[];
}

export const categoryItems = (category: DocCategory, s: ActiveSources): SourceItem[] =>
  category.sources.flatMap((src): SourceItem[] => {
    if (src.kind === 'bank') {
      return s.bank.map((b) => ({
        key: `${category.id}|bank-${b.id}`, kind: 'bank', name: b.name, integrationId: b.id, statuses: src.statuses
      }));
    }
    const list = src.kind === 'ofd' ? s.ofd : s.ecomkassa;
    if (list.length === 0) return [];
    return [{
      key: `${category.id}|${src.kind}`, kind: src.kind, name: list.map((i) => i.name).join(', '),
      orderType: src.orderType, statuses: src.statuses
    }];
  });

// Выбор пользователя: ключ строки-интеграции -> выбранные статусы.
export type Selection = Record<string, string[]>;

export const fullSelection = (s: ActiveSources): Selection => {
  const result: Selection = {};
  DOC_CATEGORIES.forEach((c) => categoryItems(c, s).forEach((item) => {
    result[item.key] = item.statuses.map((st) => st.id);
  }));
  return result;
};

export interface BackfillPlan {
  typeStatuses: Record<string, string[]>;
  hasOfd: boolean;
  bankIds: number[];
}

export const buildPlan = (selection: Selection, s: ActiveSources): BackfillPlan => {
  const typeStatuses: Record<string, string[]> = {};
  let hasOfd = false;
  const bankIds: number[] = [];
  DOC_CATEGORIES.forEach((c) => categoryItems(c, s).forEach((item) => {
    const chosen = item.statuses.filter((st) => (selection[item.key] || []).includes(st.id));
    if (chosen.length === 0) return;
    if (item.kind === 'ofd') hasOfd = true;
    else if (item.kind === 'bank' && item.integrationId) bankIds.push(item.integrationId);
    else if (item.kind === 'ecomkassa' && item.orderType) {
      const codes = new Set([...(typeStatuses[item.orderType] || []), ...chosen.flatMap((st) => st.codes)]);
      typeStatuses[item.orderType] = Array.from(codes);
    }
  }));
  return { typeStatuses, hasOfd, bankIds };
};

interface IntegrationRow {
  id: number;
  integration_name: string;
  provider_slug: string;
  status: string;
}

// Свежая проверка прямо перед запуском: интеграция могла быть отключена
// (или только что подключена) с момента открытия страницы.
export const fetchActiveSources = async (companyId: number): Promise<ActiveSources> => {
  const res = await fetch(`${functionUrls['integrations-list']}?company_id=${companyId}`);
  const data = await res.json();
  const integrations: IntegrationRow[] = data.user_integrations || [];
  const pick = (slugs: string[]) =>
    integrations
      .filter((i) => slugs.includes(i.provider_slug) && i.status === 'active')
      .map((i) => ({ id: i.id, name: i.integration_name }));
  return {
    ecomkassa: pick(['ecomkassa']),
    ofd: pick(['ofdru']),
    bank: pick(['tbank_account', 'tochka_account']),
  };
};
