import { useEffect, useState } from 'react';
import Icon from '@/components/ui/icon';
import PaymentLogos from './PaymentLogos';
import functionUrls from '../../../backend/func2url.json';

interface Operator {
  name: string;
  inn: string | null;
  ogrn?: string | null;
  address?: string | null;
  email?: string | null;
  phone?: string | null;
}

const LandingFooter = ({ showCases = false }: { showCases?: boolean }) => {
  const [operator, setOperator] = useState<Operator | null>(null);

  useEffect(() => {
    fetch(`${(functionUrls as Record<string, string>)['platform-settings']}?public=1`)
      .then((res) => res.json())
      .then((data) => setOperator(data.operator || null))
      .catch(() => {});
  }, []);

  const links = [
    { href: '/#features', label: 'Возможности' },
    { href: '/#how-it-works', label: 'Как это работает' },
    { href: '/app?section=integrations', label: 'Интеграции' },
    ...(showCases ? [{ href: '/#cases', label: 'Кейсы' }] : []),
    { href: '/#pricing', label: 'Тарифы' }
  ];

  return (
    <footer className="border-t border-border py-12">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="grid gap-10 md:grid-cols-[1fr_auto_auto] md:gap-16">
          <div className="space-y-3">
            <a href="/" className="inline-flex items-center gap-2">
              <Icon name="Zap" size={20} className="text-primary" />
              <span className="font-display font-bold text-foreground">Сверка</span>
            </a>
            <p className="text-sm text-muted-foreground max-w-xs">Сверка - платформа, которая помогает бизнесам не получать штрафы по 54-ФЗ и контролировать процесс создания правильных чеков без внимания предпринимателя и руководителей</p>
          </div>

          <div>
            <h3 className="text-sm font-semibold text-foreground mb-4">Платформа</h3>
            <ul className="grid grid-cols-2 gap-x-8 gap-y-3 sm:grid-cols-1">
              {links.map((link) => (
                <li key={link.href}>
                  <a href={link.href} className="text-sm text-muted-foreground hover:text-foreground transition-colors">
                    {link.label}
                  </a>
                </li>
              ))}
            </ul>
          </div>

          <div className="md:text-right md:max-w-sm">
            {operator && (
              <div className="mb-4">
                <p className="text-sm font-semibold text-foreground">{operator.name}</p>
                {operator.inn && <p className="text-sm text-muted-foreground mt-1">ИНН {operator.inn}</p>}
                {operator.ogrn && (
                  <p className="text-sm text-muted-foreground">
                    {operator.ogrn.length === 15 ? 'ОГРНИП' : 'ОГРН'} {operator.ogrn}
                  </p>
                )}
                {operator.address && <p className="text-sm text-muted-foreground">{operator.address}</p>}
                {operator.phone && (
                  <a href={`tel:${operator.phone.replace(/[^\d+]/g, '')}`} className="mt-2 block text-sm text-foreground hover:text-primary">
                    {operator.phone}
                  </a>
                )}
                {operator.email && (
                  <a href={`mailto:${operator.email}`} className="block text-sm text-foreground hover:text-primary">
                    {operator.email}
                  </a>
                )}
              </div>
            )}
            <div className="flex flex-col gap-2 text-sm md:items-end">
              <a href="/terms" className="text-muted-foreground hover:text-foreground transition-colors">Пользовательское соглашение</a>
              <a href="/legal" className="text-muted-foreground hover:text-foreground transition-colors">Политика обработки персональных данных</a>
              <a href="/payment" className="text-muted-foreground hover:text-foreground transition-colors">Оплата, возврат и безопасность</a>
            </div>
          </div>
        </div>

        <div className="mt-10 flex flex-col gap-4 border-t border-border pt-6 text-sm text-muted-foreground md:flex-row md:items-center md:justify-between">
          <span>© {new Date().getFullYear()} Сверка. Платформа контроля 54-ФЗ</span>
          <div className="flex flex-col gap-2 md:items-end">
            <PaymentLogos />
            <span className="text-xs">
              Платежи принимает АО «ТБанк» ·{' '}
              <a href="https://www.tbank.ru/" target="_blank" rel="noopener noreferrer" className="hover:text-foreground underline">
                tbank.ru
              </a>
            </span>
          </div>
        </div>
      </div>
    </footer>
  );
};

export default LandingFooter;