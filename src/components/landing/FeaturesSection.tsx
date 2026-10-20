import { Card, CardContent } from '@/components/ui/card';
import Icon from '@/components/ui/icon';

const FEATURES = [
  {
    icon: 'GitCompare',
    title: 'Автоматическая сверка',
    description: 'Каждый платёж сопоставляется с чеком автоматически, включая авансы и их зачёт — вручную искать расхождения не нужно.'
  },
  {
    icon: 'Plug',
    title: 'Интеграции без разработчика',
    description: 'Подключите CRM, платёжные системы, ОФД, Екомкассу и банк за несколько минут — без привлечения программистов.'
  },
  {
    icon: 'Workflow',
    title: 'Автоматизации по созданию чеков',
    description: 'Настройте правила: какой чек создавать при заказе в CRM и что делать, если чек не сформировался вовремя.'
  },
  {
    icon: 'Bell',
    title: 'Уведомления о проблемах',
    description: 'Получайте оповещения в мессенджеры, если что-то пошло не так, и ежедневный отчёт по работе касс.'
  },
  {
    icon: 'MonitorCheck',
    title: 'Контроль касс онлайн',
    description: 'Следите за статусом фискальных накопителей и работой касс в реальном времени из одного окна.'
  },
  {
    icon: 'Users',
    title: 'Гибкие роли доступа',
    description: 'Владелец приглашает бухгалтеров и сотрудников с нужными правами — один аккаунт бухгалтера может вести несколько компаний.'
  }
];

const FeaturesSection = () => {
  return (
    <section id="features" className="py-20 sm:py-28 bg-card/30">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="text-center max-w-2xl mx-auto mb-16">
          <h2 className="text-3xl sm:text-4xl font-display font-bold text-foreground mb-4">
            Всё для соответствия 54-ФЗ в одном сервисе
          </h2>
          <p className="text-lg text-muted-foreground">
            Сверка берёт на себя рутину контроля фискальных документов,
            чтобы вы не переживали за штрафы и проверки.
          </p>
        </div>

        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6">
          {FEATURES.map((feature, index) => (
            <Card
              key={feature.title}
              className="border-border bg-card hover:border-primary/50 transition-colors animate-fade-in"
              style={{ animationDelay: `${index * 0.05}s` }}
            >
              <CardContent className="p-6">
                <div className="w-12 h-12 rounded-xl bg-primary/10 flex items-center justify-center mb-4">
                  <Icon name={feature.icon as any} size={22} className="text-primary" />
                </div>
                <h3 className="text-lg font-display font-semibold text-foreground mb-2">
                  {feature.title}
                </h3>
                <p className="text-sm text-muted-foreground leading-relaxed">
                  {feature.description}
                </p>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    </section>
  );
};

export default FeaturesSection;