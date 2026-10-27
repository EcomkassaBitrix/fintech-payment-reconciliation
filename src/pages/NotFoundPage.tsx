import { useNavigate } from "@/lib/router-compat";
import { Button } from '@/components/ui/button';
import Icon from '@/components/ui/icon';
import { useAuth } from '@/contexts/AuthContext';

const ROWS = [
  { label: 'Запрошенная страница', value: '1 шт.', ok: true },
  { label: 'Найдено на сайте', value: '0 шт.', ok: false },
  { label: 'Расхождение', value: '404', ok: false }
];

const NotFoundPage = () => {
  const navigate = useNavigate();
  const { user } = useAuth();

  return (
    <div className="relative min-h-screen overflow-hidden bg-background text-foreground flex flex-col">
      <div
        className="pointer-events-none absolute inset-0 opacity-[0.07]"
        style={{
          backgroundImage:
            'linear-gradient(hsl(var(--foreground)) 1px, transparent 1px), linear-gradient(90deg, hsl(var(--foreground)) 1px, transparent 1px)',
          backgroundSize: '48px 48px',
          maskImage: 'radial-gradient(ellipse at center, black 30%, transparent 75%)',
          WebkitMaskImage: 'radial-gradient(ellipse at center, black 30%, transparent 75%)'
        }}
      />
      <div className="pointer-events-none absolute left-1/2 top-1/3 h-[420px] w-[420px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-primary/20 blur-[120px]" />

      <header className="relative z-10 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center">
        <a href="/" className="flex items-center gap-2">
          <Icon name="Zap" size={24} className="text-primary" />
          <span className="text-lg font-display font-bold">Сверка</span>
        </a>
      </header>

      <main className="relative z-10 flex-1 flex items-center justify-center px-4 py-12">
        <div className="w-full max-w-xl text-center animate-fade-in">
          <div className="inline-flex items-center gap-2 rounded-full border border-border bg-card/60 px-3 py-1 text-xs text-muted-foreground mb-6">
            <span className="h-1.5 w-1.5 rounded-full bg-destructive animate-pulse" />
            Сверка не сошлась
          </div>

          <h1 className="font-display font-semibold leading-none tracking-tight text-[96px] sm:text-[150px]">
            4<span className="text-primary">0</span>4
          </h1>

          <p className="mt-4 text-xl sm:text-2xl font-display">Такой страницы нет</p>
          <p className="mt-3 text-muted-foreground max-w-md mx-auto">
            Мы проверили все записи — эта ссылка ни с чем не совпала. Возможно, её удалили или в адресе опечатка.
          </p>

          <div className="mt-8 mx-auto max-w-sm rounded-xl border border-border bg-card/80 backdrop-blur text-left text-sm">
            {ROWS.map((row, i) => (
              <div
                key={row.label}
                className={`flex items-center justify-between gap-3 px-4 py-3 ${i > 0 ? 'border-t border-border' : ''}`}
              >
                <span className="flex items-center gap-2 text-muted-foreground">
                  <Icon
                    name={row.ok ? 'CircleCheck' : 'CircleX'}
                    size={15}
                    className={row.ok ? 'text-primary' : 'text-destructive'}
                  />
                  {row.label}
                </span>
                <span className={`font-mono ${row.ok ? 'text-foreground' : 'text-destructive'}`}>{row.value}</span>
              </div>
            ))}
          </div>

          <div className="mt-8 flex flex-col sm:flex-row items-center justify-center gap-3">
            <Button size="lg" className="gap-2 w-full sm:w-auto" onClick={() => navigate(user ? '/app' : '/')}>
              <Icon name={user ? 'LayoutDashboard' : 'Home'} size={16} />
              {user ? 'В личный кабинет' : 'На главную'}
            </Button>
            <Button size="lg" variant="outline" className="gap-2 w-full sm:w-auto" onClick={() => navigate(-1)}>
              <Icon name="ArrowLeft" size={16} />
              Назад
            </Button>
          </div>
        </div>
      </main>
    </div>
  );
};

export default NotFoundPage;
