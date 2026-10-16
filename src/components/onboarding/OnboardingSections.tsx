import Icon from '@/components/ui/icon';

const SECTIONS = [
  { icon: 'GitCompare', name: 'Сверка', text: 'Сводка: сколько денег пришло, на сколько пробиты чеки и где расхождения' },
  { icon: 'Radio', name: 'События', text: 'Журнал всего, что присылают банк, платёжные сервисы и касса' },
  { icon: 'ArrowLeftRight', name: 'Транзакции', text: 'Все платежи и поступления одним списком, с привязкой к чекам' },
  { icon: 'Workflow', name: 'Автоматизация', text: 'Правила «пришла оплата — пробить чек» и другие действия без вашего участия' },
  { icon: 'Plug', name: 'Интеграции', text: 'Подключение банка, платёжных сервисов, кассы, ОФД и CRM' },
  { icon: 'Users', name: 'Доступ', text: 'Сотрудники компании и их права' },
  { icon: 'Bell', name: 'Колокольчик', text: 'Уведомления о важном: ошибки чеков, оплаты, окончание подписки' },
  { icon: 'CreditCard', name: 'Подписка', text: 'Тариф, оплата и история платежей — кнопка в шапке' }
];

const OnboardingSections = () => (
  <div className="grid gap-3 sm:grid-cols-2">
    {SECTIONS.map((s) => (
      <div key={s.name} className="flex gap-3 rounded-lg border border-border p-3">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
          <Icon name={s.icon} size={18} />
        </div>
        <div>
          <div className="text-sm font-medium">{s.name}</div>
          <div className="text-xs text-muted-foreground">{s.text}</div>
        </div>
      </div>
    ))}
  </div>
);

export default OnboardingSections;
