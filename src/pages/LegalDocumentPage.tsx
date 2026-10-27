import { useEffect, useState } from 'react';
import { Link } from "@/lib/router-compat";
import Icon from '@/components/ui/icon';
import LandingFooter from '@/components/landing/LandingFooter';
import functionUrls from '../../backend/func2url.json';
import { LEGAL_BANK, LEGAL_EMAIL, LEGAL_SITE, LegalOperator, LegalSection, OFFER, OFFER_PREAMBLE, PAYMENT_TERMS, PRIVACY_POLICY, TERMS, operatorTitle } from '@/content/legalDocuments';

type LegalDoc = 'terms' | 'privacy' | 'payment' | 'offer';

const DOCUMENTS: Record<LegalDoc, { title: string; sections: LegalSection[]; preamble?: string[] }> = {
  offer: { title: 'Публичная оферта', sections: OFFER, preamble: OFFER_PREAMBLE },
  terms: { title: 'Пользовательское соглашение', sections: TERMS },
  privacy: { title: 'Политика в отношении обработки персональных данных', sections: PRIVACY_POLICY },
  payment: { title: 'Оплата, возврат и безопасность платежей', sections: PAYMENT_TERMS }
};

const LegalDocumentPage = ({ doc }: { doc: LegalDoc }) => {
  const { title, sections, preamble } = DOCUMENTS[doc];
  const [operator, setOperator] = useState<LegalOperator | null>(null);

  useEffect(() => {
    fetch(`${(functionUrls as Record<string, string>)['platform-settings']}?public=1`)
      .then((r) => r.json())
      .then((d) => d.operator?.name && setOperator(d.operator))
      .catch(() => undefined);
  }, []);

  const email = operator?.email || LEGAL_EMAIL;
  const phone = operator?.phone || null;
  const fill = (text: string) =>
    text
      .split('{{OPERATOR}}').join(operatorTitle(operator))
      .split('{{EMAIL}}').join(email)
      .split('{{PHONE}}').join(phone ? ` или по телефону ${phone}` : '');

  useEffect(() => {
    window.scrollTo(0, 0);
  }, [title]);

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b border-border">
        <div className="mx-auto flex min-h-16 max-w-4xl items-center justify-between gap-4 px-4 py-3 sm:px-6">
          <Link to="/" className="flex items-center gap-2">
            <Icon name="Zap" size={22} className="text-primary" />
            <span className="font-display text-lg font-bold text-foreground">Сверка</span>
          </Link>
          <nav className="flex flex-wrap justify-end gap-x-4 gap-y-1 text-xs sm:text-sm">
            <Link to="/offer" className={doc === 'offer' || doc === 'terms' ? 'text-primary' : 'text-muted-foreground hover:text-foreground'}>
              Оферта
            </Link>
            <Link to="/legal" className={doc === 'privacy' ? 'text-primary' : 'text-muted-foreground hover:text-foreground'}>
              Политика ПДн
            </Link>
            <Link to="/payment" className={doc === 'payment' ? 'text-primary' : 'text-muted-foreground hover:text-foreground'}>
              Оплата и возврат
            </Link>
          </nav>
        </div>
      </header>

      <main className="mx-auto max-w-4xl px-4 py-10 sm:px-6">
        <div className="mb-2 text-sm text-muted-foreground">Документы</div>
        <h1 className="mb-8 font-display text-3xl font-bold text-foreground">{title}</h1>
        {preamble && (
          <div className="mb-8 space-y-2 text-sm leading-relaxed text-muted-foreground">
            {preamble.map((item, i) => (
              <p key={i} className={i === 0 ? 'font-medium text-foreground' : undefined}>{fill(item)}</p>
            ))}
          </div>
        )}
        <div className="space-y-8">
          {sections.map((s) => (
            <section key={s.title}>
              <h2 className="mb-3 text-lg font-semibold text-foreground">{s.title}</h2>
              <div className="space-y-2 text-sm leading-relaxed text-muted-foreground">
                {s.items.map((item, i) => (
                  <p key={i}>{fill(item)}</p>
                ))}
              </div>
            </section>
          ))}

          <section className="rounded-xl border border-border bg-card p-5">
            <h2 className="mb-3 text-lg font-semibold text-foreground">
              {doc === 'offer' ? '15. Реквизиты Лицензиара' : 'Реквизиты Оператора'}
            </h2>
            <dl className="grid gap-x-6 gap-y-1.5 text-sm sm:grid-cols-[auto_1fr]">
              <dt className="text-muted-foreground">Наименование</dt>
              <dd className="text-foreground">{operatorTitle(operator).replace(/ \((ОГРНИП|ОГРН) .*\)$/, '')}</dd>
              {operator?.inn && (
                <>
                  <dt className="text-muted-foreground">ИНН</dt>
                  <dd className="text-foreground">{operator.inn}</dd>
                </>
              )}
              {operator?.ogrn && (
                <>
                  <dt className="text-muted-foreground">{operator.ogrn.length === 15 ? 'ОГРНИП' : 'ОГРН'}</dt>
                  <dd className="text-foreground">{operator.ogrn}</dd>
                </>
              )}
              {operator?.address && (
                <>
                  <dt className="text-muted-foreground">Адрес</dt>
                  <dd className="text-foreground">{operator.address}</dd>
                </>
              )}
              <dt className="text-muted-foreground">Эл. почта</dt>
              <dd>
                <a href={`mailto:${email}`} className="text-primary hover:underline">{email}</a>
              </dd>
              {phone && (
                <>
                  <dt className="text-muted-foreground">Телефон</dt>
                  <dd>
                    <a href={`tel:${phone.replace(/[^\d+]/g, '')}`} className="text-primary hover:underline">{phone}</a>
                  </dd>
                </>
              )}
              {doc === 'offer' && (
                <>
                  <dt className="text-muted-foreground">Расчётный счёт</dt>
                  <dd className="text-foreground">{LEGAL_BANK.account}</dd>
                  <dt className="text-muted-foreground">Банк</dt>
                  <dd className="text-foreground">{LEGAL_BANK.bank}</dd>
                  <dt className="text-muted-foreground">БИК</dt>
                  <dd className="text-foreground">{LEGAL_BANK.bik}</dd>
                  <dt className="text-muted-foreground">Корр. счёт</dt>
                  <dd className="text-foreground">{LEGAL_BANK.corr}</dd>
                </>
              )}
              <dt className="text-muted-foreground">Сайт</dt>
              <dd>
                <a href={LEGAL_SITE} className="text-primary hover:underline">{LEGAL_SITE.replace('https://', '')}</a>
              </dd>
            </dl>
          </section>
        </div>
      </main>

      <LandingFooter />
    </div>
  );
};

export default LegalDocumentPage;