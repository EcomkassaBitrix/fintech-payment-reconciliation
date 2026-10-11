import { Button } from '@/components/ui/button';
import Icon from '@/components/ui/icon';
import { pluralDays } from '@/lib/trialDays';

const HERO_STATS = [
  { value: '0 ₽', label: 'Штрафов за пропущенные чеки' },
  { value: '100%', label: 'Платежей сверено автоматически' },
  { value: '24/7', label: 'Контроль касс без бухгалтера' }
];

const HeroSection = ({ onCtaClick, trialDays }: { onCtaClick: () => void; trialDays: number }) => {
  return (
    <section className="relative overflow-hidden pt-16 pb-24 sm:pt-24 sm:pb-32">
      <div className="absolute inset-0 -z-10">
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[600px] h-[600px] bg-primary/10 rounded-full blur-3xl" />
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="grid lg:grid-cols-2 gap-12 items-center">
          <div className="animate-fade-in">
            <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-primary/10 border border-primary/20 mb-6">
              <Icon name="ShieldCheck" size={14} className="text-primary" />
              <span className="text-xs font-medium text-primary">Платформа контроля 54-ФЗ</span>
            </div>

            <h1 className="text-4xl sm:text-5xl lg:text-6xl font-display font-bold text-foreground leading-tight mb-6">
              Каждый платёж —<br />
              <span className="text-primary">с чеком.</span> Всегда.
            </h1>

            <p className="text-lg text-muted-foreground mb-8 max-w-xl">
              Без штрафов и без бухгалтера на ручной сверке. Сверка каждый день сводит платежи
              без вашего участия из CRM, банков и эквайринга с чеками из ОФД и кассы, сама находит
              пропущенные чеки и показывает, с какой суммы платить налоги без доначислений.
            </p>

            <div className="flex flex-col sm:flex-row gap-4 mb-8">
              <Button size="lg" onClick={onCtaClick} className="text-base h-14 px-8 gap-2">
                <Icon name="Rocket" size={18} />
                Попробовать {pluralDays(trialDays)} бесплатно
              </Button>
              <Button size="lg" variant="outline" className="text-base h-14 px-8 gap-2" asChild>
                <a href="#how-it-works">
                  <Icon name="PlayCircle" size={18} />
                  Как это работает
                </a>
              </Button>
            </div>

            <p className="text-xs text-muted-foreground">
              Без банковской карты. Отменить можно в любой момент.
            </p>
          </div>

          <div className="relative animate-scale-in">
            <div className="absolute inset-0 bg-gradient-to-tr from-primary/20 to-transparent rounded-3xl blur-2xl" />
            <div className="relative mx-auto w-full max-w-2xl">
              <div className="relative rounded-t-xl sm:rounded-t-2xl bg-zinc-800 p-[2.2%] pb-[2.8%] shadow-2xl ring-1 ring-white/10">
                <span className="absolute left-1/2 top-[0.8%] h-[1%] w-[1%] min-h-1 min-w-1 -translate-x-1/2 rounded-full bg-zinc-600" />
                <div className="overflow-hidden rounded-sm bg-black aspect-[1600/906]">
                  <img
                    src="/hero-dashboard.webp"
                    alt="Личный кабинет Сверки: платежи, чеки и деньги на счёте сходятся на 100%"
                    className="h-full w-full object-cover object-left-top"
                  />
                </div>
              </div>
              <div className="relative -mx-[6%] h-[0.9rem] sm:h-[1.1rem] rounded-b-[40%_100%] bg-gradient-to-b from-zinc-600 to-zinc-800 shadow-xl">
                <span className="absolute left-1/2 top-0 h-[40%] w-[16%] -translate-x-1/2 rounded-b-md bg-zinc-900/70" />
              </div>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-3 gap-6 mt-20 pt-10 border-t border-border">
          {HERO_STATS.map((stat) => (
            <div key={stat.label} className="text-center">
              <div className="text-2xl sm:text-3xl font-display font-bold text-primary mb-1">{stat.value}</div>
              <div className="text-xs sm:text-sm text-muted-foreground">{stat.label}</div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};

export default HeroSection;