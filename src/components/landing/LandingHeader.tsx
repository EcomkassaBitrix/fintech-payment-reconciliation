import { useState } from 'react';
import { Button } from '@/components/ui/button';
import Icon from '@/components/ui/icon';
import { pluralDays } from '@/lib/trialDays';
import { useNavigate } from "@/lib/router-compat";
import { useAuth } from '@/contexts/AuthContext';

const NAV_LINKS = [
  { href: '/#features', label: 'Возможности' },
  { href: '/#how-it-works', label: 'Как это работает' },
  { href: '/pricing', label: 'Тарифы' },
  { href: '/#faq', label: 'FAQ' }
];

const CASES_LINK = { href: '/#cases', label: 'Кейсы' };

interface LandingHeaderProps {
  onCtaClick: () => void;
  trialDays: number;
  showCases?: boolean;
}

const LandingHeader = ({ onCtaClick, trialDays, showCases = false }: LandingHeaderProps) => {
  const navigate = useNavigate();
  const navLinks = showCases ? [...NAV_LINKS.slice(0, 2), CASES_LINK, ...NAV_LINKS.slice(2)] : NAV_LINKS;
  const { user } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <header className="sticky top-0 z-50 bg-background/90 backdrop-blur-md border-b border-border">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        <a href="/" className="flex items-center gap-2 shrink-0">
          <Icon name="Zap" size={24} className="text-primary" />
          <span className="text-lg font-display font-bold text-foreground">Сверка</span>
        </a>

        <nav className="hidden md:flex items-center">
          {navLinks.map((link) => (
            <a
              key={link.href}
              href={link.href}
              style={{ marginRight: '2rem' }}
              className="text-sm font-medium text-muted-foreground hover:text-foreground transition-colors whitespace-nowrap"
            >
              {link.label}
            </a>
          ))}
        </nav>

        <div className="hidden md:flex items-center gap-3">
          {user ? (
            <Button onClick={() => navigate('/app')} className="gap-2">
              <Icon name="Zap" size={16} />
              В кабинет
            </Button>
          ) : (
            <>
              <Button variant="ghost" onClick={() => navigate('/login')}>
                Войти
              </Button>
              <Button onClick={onCtaClick} className="gap-2">
                Попробовать {pluralDays(trialDays)} бесплатно
              </Button>
            </>
          )}
        </div>

        <button
          className="md:hidden p-2 text-foreground"
          onClick={() => setMenuOpen(!menuOpen)}
          aria-label="Открыть меню"
        >
          <Icon name={menuOpen ? 'X' : 'Menu'} size={24} />
        </button>
      </div>

      {menuOpen && (
        <div className="md:hidden border-t border-border bg-background px-4 py-4 space-y-4 animate-fade-in">
          {navLinks.map((link) => (
            <a
              key={link.href}
              href={link.href}
              className="block text-sm font-medium text-muted-foreground hover:text-foreground"
              onClick={() => setMenuOpen(false)}
            >
              {link.label}
            </a>
          ))}
          <div className="flex flex-col gap-2 pt-2">
            {user ? (
              <Button onClick={() => navigate('/app')} className="gap-2">
                <Icon name="Zap" size={16} />
                В кабинет
              </Button>
            ) : (
              <>
                <Button variant="outline" onClick={() => navigate('/login')}>
                  Войти
                </Button>
                <Button onClick={onCtaClick}>
                  Попробовать {pluralDays(trialDays)} бесплатно
                </Button>
              </>
            )}
          </div>
        </div>
      )}
    </header>
  );
};

export default LandingHeader;