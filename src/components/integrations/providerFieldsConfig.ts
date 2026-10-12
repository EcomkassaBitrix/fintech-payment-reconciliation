export interface Provider {
  id: number;
  name: string;
  slug: string;
  logo_url: string;
  description: string;
}

export interface Category {
  id: number;
  name: string;
  slug: string;
  icon: string;
  description?: string;
  providers: Provider[];
}

export type ConfigValue = string | number | boolean | string[];
export type ConfigState = Record<string, ConfigValue>;

export interface UserIntegration {
  id: number;
  integration_name: string;
  provider_id: number;
  config: ConfigState;
  webhook_settings: Record<string, boolean>;
  forward_url?: string;
}

export type FieldType = 'text' | 'password' | 'number' | 'checkbox' | 'select' | 'multiselect' | 'keywords';

export interface FieldOption {
  value: string;
  label: string;
}

export interface FieldConfig {
  key: string;
  label: string;
  type: FieldType;
  placeholder?: string;
  hint?: string;
  default?: ConfigValue;
  required?: boolean;
  options?: FieldOption[];
  // Маска/проверка текстового поля: normalize - чистит ввод, validate - текст ошибки или null.
  normalize?: (value: string) => string;
  validate?: (value: string) => string | null;
}

// Входящий вебхук Битрикс24: https://портал/rest/<id пользователя>/<код>/.
// Лишний метод в конце (profile.json, crm.deal.list и т.п.) отрезаем, пробелы убираем.
export const normalizeBitrixWebhook = (value: string) => {
  const v = value.replace(/\s+/g, '');
  // Отрезаем только метод с точкой в конце (…/код/profile.json) - обычный ввод по буквам не трогаем.
  const m = v.match(/^(https?:\/\/[^/]+\/rest\/\d+\/[A-Za-z0-9]+)\/[\w.]*\.[\w.]*\/?$/);
  return m ? `${m[1]}/` : v;
};

export const validateBitrixWebhook = (value: string) => {
  const v = value.trim();
  if (!v) return null;
  if (v.includes('functions.poehali.dev'))
    return 'Это наш адрес для исходящих хуков — он указывается в Битрикс24. Сюда нужен входящий вебхук портала';
  if (!/^https:\/\//.test(v)) return 'Адрес должен начинаться с https://';
  if (!/^https:\/\/[^/]+\/rest\/\d+\/[A-Za-z0-9]+\/?$/.test(v))
    return 'Нужен адрес вида https://ваш-портал.bitrix24.ru/rest/1/код/';
  return null;
};

export const SYNC_INTERVAL_OPTIONS: FieldOption[] = [
  { value: '1', label: 'Раз в час' },
  { value: '12', label: 'Раз в 12 часов' },
  { value: '24', label: 'Раз в сутки (в 00:00 по времени компании)' }
];

export const ECOMKASSA_PROTOCOL_OPTIONS: FieldOption[] = [
  { value: 'v4', label: 'v4 (текущая)' },
  { value: 'v5', label: 'v5' }
];

export const DEFAULT_WEBHOOK_SETTINGS: Record<string, boolean> = {
  notify_on_authorized: true,
  notify_on_confirmed: true,
  notify_on_rejected: true,
  notify_on_refunded: true,
  notify_on_canceled: true
};

export const TBANK_NOTIFY_OPTIONS = [
  { key: 'notify_on_authorized', label: 'Авторизован (AUTHORIZED)' },
  { key: 'notify_on_confirmed', label: 'Подтверждён (CONFIRMED)' },
  { key: 'notify_on_rejected', label: 'Отклонён (REJECTED)' },
  { key: 'notify_on_refunded', label: 'Возврат (REFUNDED)' },
  { key: 'notify_on_canceled', label: 'Отменён (CANCELED)' }
];

// Шлюз Екомкассы отдаёт статусы 0-4 (создан/оплачен/подтверждён/отменён/просрочен),
// без отдельного события возврата - поэтому REFUNDED здесь не показываем.
export const ECOMKASSA_GATEWAY_NOTIFY_OPTIONS = [
  { key: 'notify_on_authorized', label: 'Оплачен, ожидает подтверждения' },
  { key: 'notify_on_confirmed', label: 'Оплачен, подтверждён' },
  { key: 'notify_on_rejected', label: 'Не оплачен (истекло время)' },
  { key: 'notify_on_canceled', label: 'Отменён' }
];

const BANK_ACCOUNT_FIELDS: FieldConfig[] = [
  { key: 'account_number', label: 'Номер расчётного счёта', type: 'text', placeholder: '40702810000000000000' },
  { key: 'inn', label: 'ИНН организации', type: 'text', placeholder: '1234567890' },
  { key: 'api_token', label: 'Токен API банка', type: 'password', hint: 'Получите в личном кабинете банка в разделе API/интеграции' }
];

// auth_method/api_token/account_number для tochka_account не входят в общий
// список полей - выбор способа авторизации (JWT/OAuth 2.0), сам токен и счёт
// вводятся в TochkaAuthMethodPicker: по JWT-токену запрашивается список счетов
// компании (Get Accounts List), номер счёта выбирается из него, а не вводится
// руками. ИНН отдельно не спрашиваем - он уже есть в карточке компании и в
// синхронизации выписки нигде не используется (Точка идентифицирует счёт по
// accountId из самого токена, а не по ИНН из формы). purpose_keywords и
// sync_interval_hours - те же поля, что и у tbank_account: backend
// (bank-statement-sync/fetch_tochka_account_statement) уже фильтрует операции
// по ключевым словам назначения платежа одинаково для обоих банков.
const TOCHKA_ACCOUNT_FIELDS: FieldConfig[] = [
  {
    key: 'purpose_keywords',
    label: 'Учитывать назначения платежа по ключевым словам',
    type: 'keywords',
    default: '',
    required: false,
    placeholder: 'эквайринг, сбп, оплата заказа',
    hint: 'Через запятую. Операция загрузится, если назначение платежа содержит хотя бы одно из слов. Оставьте пустым, чтобы загружать все операции'
  },
  {
    key: 'sync_interval_hours',
    label: 'Периодичность синхронизации',
    type: 'select',
    options: SYNC_INTERVAL_OPTIONS,
    default: '24',
    required: false,
    hint: 'Как часто загружать выписку автоматически. «Синхронизировать сейчас» работает в любой момент'
  }
];

export const ALFABANK_NOTIFY_OPTIONS = [
  { key: 'notify_on_authorized', label: 'Средства удержаны (approved)' },
  { key: 'notify_on_confirmed', label: 'Оплачен (deposited) — картой и по СБП' },
  { key: 'notify_on_rejected', label: 'Отклонён (declined)' },
  { key: 'notify_on_refunded', label: 'Возврат (refunded)' },
  { key: 'notify_on_canceled', label: 'Отменён (reversed)' }
];

export const YOOKASSA_NOTIFY_OPTIONS = [
  { key: 'notify_on_confirmed', label: 'Платёж успешен (payment.succeeded)' },
  { key: 'notify_on_authorized', label: 'Ждёт подтверждения (payment.waiting_for_capture)' },
  { key: 'notify_on_canceled', label: 'Отменён магазином (payment.canceled)' },
  { key: 'notify_on_rejected', label: 'Не оплачен (payment.canceled — отказ банка, истёк срок)' },
  { key: 'notify_on_refunded', label: 'Возврат (refund.succeeded)' }
];

// Варианты «Уведомления о статусах платежей» по провайдеру - и для настроек интеграции, и для запуска сценария.
export const notifyOptionsFor = (slug?: string) =>
  slug === 'tbank'
    ? TBANK_NOTIFY_OPTIONS
    : slug === 'alfabank'
      ? ALFABANK_NOTIFY_OPTIONS
      : slug === 'yookassa'
      ? YOOKASSA_NOTIFY_OPTIONS
      : slug === 'tochka_acquiring'
        ? TOCHKA_ACQUIRING_NOTIFY_OPTIONS
        : slug === 'ecomkassa_gateway'
          ? ECOMKASSA_GATEWAY_NOTIFY_OPTIONS
          : [];

// Ключ настройки уведомления -> статус платежа в нашей базе.
export const NOTIFY_KEY_STATUS: Record<string, string> = {
  notify_on_authorized: 'AUTHORIZED',
  notify_on_confirmed: 'CONFIRMED',
  notify_on_rejected: 'REJECTED',
  notify_on_refunded: 'REFUNDED',
  notify_on_canceled: 'CANCELED'
};

const ALFABANK_ENV_OPTIONS: FieldOption[] = [
  { value: 'prod', label: 'Боевой — payment.alfabank.ru (логин с префиксом r-)' },
  { value: 'prod_pay', label: 'Боевой — pay.alfabank.ru (логин без префикса)' },
  { value: 'test', label: 'Тестовый — alfa.rbsuat.com' }
];

export const TOCHKA_ACQUIRING_NOTIFY_OPTIONS = [
  { key: 'notify_on_authorized', label: 'Средства заморожены (двухэтапная оплата)' },
  { key: 'notify_on_confirmed', label: 'Оплачен — картой, по СБП, Долями' }
];

export const MOYKLASS_STAGE_OPTIONS: FieldOption[] = [
  { value: 'payment_new', label: 'Принят платёж → чек предоплаты (аванс)' },
  { value: 'debit_new', label: 'Новое списание → чек зачёта аванса (услуга оказана)' }
];

export const MOYKLASS_STAGE_HINTS: Record<string, { event: string; title: string; template: string }> = {
  payment_new: { event: 'Принят платеж', title: 'Принят платёж', template: 'prepayment_service' },
  debit_new: { event: 'Новое списание у ученика', title: 'Новое списание', template: 'advance_offset_service' }
};

export const RK_STAGE_OPTIONS: FieldOption[] = [
  { value: 'income', label: 'Платёж гостя → чек предоплаты' },
  { value: 'refund', label: 'Возврат гостю → чек возврата предоплаты' }
];

export const RK_STAGE_TITLES: Record<string, string> = { income: 'Платёж гостя', refund: 'Возврат гостю' };

export const RK_PAYMENT_SYSTEM_OPTIONS: FieldOption[] = [
  { value: 'manual', label: 'Вручную (наличные, переводы)' },
  { value: 'moneta', label: 'Монета' },
  { value: 'moneta_le', label: 'Монета (юрлицо)' },
  { value: 'yandex_kassa', label: 'ЮKassa' }
];

export const PROVIDER_FIELDS: Record<string, FieldConfig[]> = {
  // Токен, торговая точка и способ входа (JWT / вход через Точку) - в TochkaAcquiringPicker.
  tochka_acquiring: [],
  alfabank: [
    { key: 'environment', label: 'Сервер банка', type: 'select', options: ALFABANK_ENV_OPTIONS, default: 'prod', required: false, hint: 'Адрес зависит от логина: уточните у поддержки Альфа-Банка, если не уверены' },
    { key: 'user_name', label: 'Логин API-пользователя', type: 'text', placeholder: 'r-shop-api', hint: 'Учётная запись магазина с окончанием -api из письма Альфа-Банка' },
    { key: 'password', label: 'Пароль API-пользователя', type: 'password', placeholder: '•••••••••', hint: 'Логин и пароль проверим у банка при сохранении' },
    { key: 'callback_secret', label: 'Callback токен (необязательно)', type: 'password', placeholder: '•••••••••', required: false, hint: 'ЛК банка → Callback уведомления → тип подписи «Симметричный» → кнопка «Сгенерировать» рядом с полем «Callback токен» → скопируйте токен сюда. Пусто — уведомления принимаются без проверки подписи' }
  ],
  yookassa: [
    { key: 'shop_id', label: 'shopId', type: 'text', placeholder: '123456', hint: 'ЮKassa → Интеграция → Ключи API → shopId (только цифры)' },
    { key: 'secret_key', label: 'Секретный ключ', type: 'password', placeholder: 'live_•••••••••', hint: 'Там же: «Выпустить секретный ключ». Ключ начинается с live_ (боевой) или test_ (тестовый магазин). По нему проверяем каждое уведомление в ЮKassa' }
  ],
  tbank: [
    { key: 'terminal_id', label: 'Terminal ID', type: 'text', placeholder: '1234567890', hint: 'Найдите в ЛК Т-Банк → Настройки → Терминалы' },
    { key: 'terminal_password', label: 'Terminal Password', type: 'password', placeholder: '•••••••••', hint: 'Terminal ID и пароль проверим у Т-Банка при сохранении' }
  ],
  // Токен и касса вводятся в OfdKktPicker: по токену и ИНН компании загружаем список касс из OFD.RU.
  ofdru: [],
  bitrix24: [
    {
      key: 'webhook_url',
      label: 'Входящий вебхук Битрикс24',
      type: 'text',
      placeholder: 'https://ваш-портал.bitrix24.ru/rest/1/код/',
      hint: 'Формат https://ваш-портал.bitrix24.ru/rest/1/код/ · Битрикс24 → Разработчикам → Другое → Входящий вебхук. Права: crm',
      normalize: normalizeBitrixWebhook,
      validate: validateBitrixWebhook
    }
  ],
  amocrm: [
    { key: 'subdomain', label: 'Поддомен AmoCRM', type: 'text', placeholder: 'yourcompany', hint: 'Из адреса вида yourcompany.amocrm.ru' },
    { key: 'api_key', label: 'Долгосрочный токен доступа', type: 'password', hint: 'AmoCRM → Настройки → Интеграции → Создать интеграцию' }
  ],
  // account_number для tbank_account не входит в общий список полей -
  // выбирается отдельным компонентом (TbankAccountPicker): автоматически из
  // списка счетов, если владелец подтвердил доступ через Т-Бизнес, либо вручную.
  tbank_account: [
    {
      key: 'purpose_keywords',
      label: 'Учитывать назначения платежа по ключевым словам',
      type: 'keywords',
      default: '',
      required: false,
      placeholder: 'эквайринг, сбп, оплата заказа',
      hint: 'Через запятую. Операция загрузится, если назначение платежа содержит хотя бы одно из слов. Оставьте пустым, чтобы загружать все операции'
    },
    {
      key: 'sync_interval_hours',
      label: 'Периодичность синхронизации',
      type: 'select',
      options: SYNC_INTERVAL_OPTIONS,
      default: '24',
      required: false,
      hint: 'Как часто загружать выписку автоматически. «Синхронизировать сейчас» работает в любой момент'
    }
  ],
  tochka_account: TOCHKA_ACCOUNT_FIELDS,
  modulbank_account: BANK_ACCOUNT_FIELDS,
  // login/password/store_id для ecomkassa не входят в общий список полей -
  // логин и пароль вводятся в EcomkassaStorePicker, который по ним получает
  // токен и список магазинов, а сам магазин выбирается там же из списка.
  ecomkassa: [
    {
      key: 'protocol_version',
      label: 'Версия протокола',
      type: 'select',
      options: ECOMKASSA_PROTOCOL_OPTIONS,
      default: 'v4',
      required: false,
      hint: 'Уточните у Екомкассы, если не уверены — по умолчанию v4'
    }
  ],
  // Платёжный шлюз (payments.ecomkassa.ru) не требует токенов - у нас нет
  // прямого доступа к банку, шлюз лишь присылает статус платежа по callback_url.
  // Чек по UUID платежа он находит сам в активной кассе "Екомкасса" той же
  // компании - отдельно указывать магазин здесь не нужно.
  ecomkassa_gateway: [],
  // Одна интеграция RealtyCalendar = один этап со своими фильтрами и своим адресом вебхука.
  realtycalendar: [
    {
      key: 'stage',
      label: 'Этап, который обрабатывает интеграция',
      type: 'select',
      default: 'income',
      options: RK_STAGE_OPTIONS,
      hint: 'RealtyCalendar присылает бронь целиком при любом изменении — мы берём из неё только новые платежи этого этапа. Для другого этапа подключите ещё одну интеграцию со своим адресом вебхука'
    },
    {
      key: 'payment_systems',
      label: 'Платёжные системы, по которым создавать чеки',
      type: 'multiselect',
      default: ['manual'],
      options: RK_PAYMENT_SYSTEM_OPTIONS,
      hint: 'Онлайн-оплаты через Монету или ЮKassa обычно уже пробивает касса платёжной системы — не выбирайте их, иначе чеки задвоятся'
    },
    {
      key: 'include_deposits',
      label: 'Пробивать чеки по залогам',
      type: 'checkbox',
      default: false,
      required: false
    }
  ],
  // Одна интеграция «Мой Класс» = один этап (событие вебхука). Зачёт аванса по списаниям -
  // отдельной интеграцией со своим адресом вебхука, чтобы события не смешивались.
  moyklass: [
    {
      key: 'api_key',
      label: 'Ключ API «Мой Класс»',
      type: 'password',
      hint: '«Мой Класс» → Настройки → API → создать ключ'
    },
    {
      key: 'stage',
      label: 'Этап (событие), который обрабатывает интеграция',
      type: 'select',
      default: 'payment_new',
      options: MOYKLASS_STAGE_OPTIONS,
      hint: 'Оплата абонемента — это аванс (чек предоплаты). Когда занятие проведено, «Мой Класс» списывает его стоимость — по этому списанию пробивается чек полного расчёта с зачётом аванса. Для каждого этапа — своя интеграция со своим адресом вебхука'
    }
  ]
};

// Провайдеры, для которых наш сервис принимает входящие вебхуки.
// Только для них имеет смысл показывать URL для вебхука и переадресацию.
const PROVIDERS_WITH_INCOMING_WEBHOOK = ['tbank', 'alfabank', 'yookassa', 'tochka_acquiring', 'ecomkassa_gateway', 'moyklass', 'realtycalendar'];

export const buildDefaultConfig = (slug: string): ConfigState => {
  const fields = PROVIDER_FIELDS[slug] || [];
  const config: ConfigState = {};
  fields.forEach((field) => {
    config[field.key] = field.default ?? (field.type === 'checkbox' ? false : '');
  });
  return config;
};

// Платёжки, по которым чек делаем сами из корзины: после подключения предлагаем сценарий чеков.
// Шлюз Екомкассы сюда не входит - чек по нему пробивает сама Екомкасса.
const PROVIDERS_WITH_RECEIPT_SCENARIO = ['tbank', 'alfabank', 'yookassa', 'tochka_acquiring', 'moyklass', 'realtycalendar'];
export const suggestsReceiptScenario = (slug?: string) => !!slug && PROVIDERS_WITH_RECEIPT_SCENARIO.includes(slug);

export const acceptsIncomingWebhook = (slug?: string) => !!slug && PROVIDERS_WITH_INCOMING_WEBHOOK.includes(slug);