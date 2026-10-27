import { useState, useEffect } from 'react';
import { chosenTariff, forgetTariff } from '@/lib/chosenTariff';
import { useNavigate } from "@/lib/router-compat";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import Icon from '@/components/ui/icon';
import { useToast } from '@/hooks/use-toast';
import { useAuth } from '@/contexts/AuthContext';
import { GOALS, reachGoal } from '@/lib/metrika';
import functionUrls from '../../backend/func2url.json';
import { sanitizeInn, isValidInn, getInnHint } from '@/lib/formatters';
import PendingPromoNotice from '@/components/PendingPromoNotice';
import { startOnboarding } from '@/lib/onboarding';

interface CompanyLookupData {
  inn: string;
  kpp: string | null;
  ogrn: string;
  full_name: string;
  short_name: string;
  address: string;
}

const CreateCompany = () => {
  const { user, companies, refreshCompanies, setCurrentCompanyId, logout } = useAuth();
  const { toast } = useToast();
  const navigate = useNavigate();
  const [inn, setInn] = useState('');
  const [isSearching, setIsSearching] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [foundCompany, setFoundCompany] = useState<CompanyLookupData | null>(null);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [usage, setUsage] = useState<{ owned: number; max_companies: number | null } | null>(null);

  // Первый вход: список компаний мог устареть (например, сотрудник только что принял
  // приглашение) - перепроверяем, и если компания уже есть, сразу открываем кабинет.
  const [openedWithoutCompanies] = useState(companies.length === 0);
  useEffect(() => {
    if (user && openedWithoutCompanies) refreshCompanies(user.user_id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.user_id]);
  useEffect(() => {
    if (openedWithoutCompanies && companies.length > 0) navigate('/app', { replace: true });
  }, [openedWithoutCompanies, companies.length, navigate]);

  // Сколько компаний уже создано и сколько разрешает тариф.
  useEffect(() => {
    if (!user) return;
    fetch(`${functionUrls['companies-list']}?view=limit&user_id=${user.user_id}`)
      .then((res) => res.json())
      .then((data) => data.success && setUsage({ owned: data.owned, max_companies: data.max_companies }))
      .catch(() => {});
  }, [user]);

  const limitReached = !!usage && usage.max_companies !== null && usage.owned >= usage.max_companies;
  const hasCompanies = !!usage && usage.owned > 0;

  const handleSearch = async () => {
    if (!isValidInn(inn)) return;

    setIsSearching(true);
    setSearchError(null);
    setFoundCompany(null);

    try {
      const response = await fetch(`${functionUrls['companies-list']}?inn=${inn}`);
      const data = await response.json();

      if (response.ok && data.success) {
        setFoundCompany(data.company_data);
      } else {
        setSearchError(data.error || 'Не удалось найти компанию по этому ИНН');
      }
    } catch (error) {
      setSearchError('Проверьте интернет-соединение и попробуйте снова');
    } finally {
      setIsSearching(false);
    }
  };

  const handleCreate = async () => {
    if (!user || !foundCompany) return;

    setIsCreating(true);
    try {
      const response = await fetch(functionUrls['companies-list'], {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: user.user_id,
          name: foundCompany.short_name,
          inn: foundCompany.inn,
          kpp: foundCompany.kpp,
          ogrn: foundCompany.ogrn,
          full_name: foundCompany.full_name,
          legal_address: foundCompany.address,
          tariff_slug: chosenTariff()
        })
      });

      const data = await response.json();

      if (response.ok && data.success) {
        if (data.trial_started) {
          reachGoal(GOALS.trialStarted, { tariff: data.trial_tariff_slug, tariff_name: data.trial_tariff_name });
        }
        forgetTariff();
        startOnboarding(data.company_id);
        await refreshCompanies();
        setCurrentCompanyId(data.company_id);
        toast({ title: 'Компания создана', description: data.name });
        navigate('/app', { replace: true });
      } else {
        toast({
          title: 'Ошибка',
          description: data.error || 'Не удалось создать компанию',
          variant: 'destructive'
        });
      }
    } catch (error) {
      toast({
        title: 'Ошибка подключения',
        description: 'Проверьте интернет-соединение',
        variant: 'destructive'
      });
    } finally {
      setIsCreating(false);
    }
  };

  const handleInnChange = (value: string) => {
    setInn(sanitizeInn(value));
    setFoundCompany(null);
    setSearchError(null);
  };

  useEffect(() => {
    if (isValidInn(inn)) {
      handleSearch();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [inn]);

  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        <div className="mb-8 text-center animate-fade-in">
          <a href="/" className="flex items-center justify-center gap-2 mb-2">
            <Icon name="Zap" size={32} className="text-primary" />
            <h1 className="text-3xl font-display font-bold text-foreground">Сверка</h1>
          </a>
          <p className="text-sm text-muted-foreground">
            {hasCompanies ? 'Добавьте ещё одну компанию' : 'Добавьте свою первую компанию'}
          </p>
        </div>

        <PendingPromoNotice className="mb-4" hint="Создайте компанию — подписка по промокоду включится сразу" />

        <Card className="relative shadow-2xl border-0 animate-scale-in">
          {hasCompanies && (
            <Button
              variant="ghost"
              size="icon"
              onClick={() => navigate('/app')}
              className="absolute right-3 top-3 h-8 w-8 text-muted-foreground hover:text-foreground"
              aria-label="Закрыть"
              title="Закрыть и вернуться к компаниям"
            >
              <Icon name="X" size={18} />
            </Button>
          )}
          <CardHeader className="text-center pb-4">
            <CardTitle className="text-2xl font-display">Создание компании</CardTitle>
            <CardDescription className="text-base">
              Введите ИНН — мы найдём компанию автоматически
            </CardDescription>
          </CardHeader>

          <CardContent className="space-y-6">
            {usage && usage.max_companies !== null && (
              <div
                className={`rounded-lg border p-3 ${
                  limitReached ? 'border-warning/30 bg-warning/10' : 'border-border bg-muted/30'
                }`}
              >
                <div className="flex items-center justify-between gap-3 text-sm">
                  <span className="flex items-center gap-2 text-muted-foreground">
                    <Icon name="Building2" size={16} />
                    Компаний по тарифу
                  </span>
                  <span className={`font-semibold ${limitReached ? 'text-warning' : 'text-foreground'}`}>
                    Использовано {usage.owned} из {usage.max_companies}
                  </span>
                </div>
                {limitReached && (
                  <>
                    <p className="mt-2 text-sm text-muted-foreground">
                      Лимит компаний исчерпан. Чтобы добавить новую, перейдите на тариф с большим числом компаний.
                    </p>
                    <Button
                      variant="outline"
                      size="sm"
                      className="mt-3 w-full"
                      onClick={() => navigate('/app?section=subscription')}
                    >
                      <Icon name="ArrowUpCircle" size={16} className="mr-2" />
                      Сменить тариф
                    </Button>
                  </>
                )}
              </div>
            )}

            <div className="space-y-2">
              <Label>ИНН компании</Label>
              <div className="flex gap-2">
                <Input
                  inputMode="numeric"
                  placeholder="7712345678"
                  value={inn}
                  onChange={(e) => handleInnChange(e.target.value)}
                  maxLength={12}
                  className="h-12"
                />
                <Button
                  onClick={handleSearch}
                  disabled={!isValidInn(inn) || isSearching}
                  variant="secondary"
                  className="h-12 px-4 shrink-0"
                >
                  {isSearching ? (
                    <Icon name="Loader2" size={18} className="animate-spin" />
                  ) : (
                    <Icon name="Search" size={18} />
                  )}
                </Button>
              </div>
              {(inn.length === 11 || getInnHint(inn)) && (
                <p className={`text-xs ${inn.length === 11 ? 'text-destructive' : 'text-muted-foreground'}`}>
                  {inn.length === 11 ? 'ИНН должен содержать 10 (юрлицо) или 12 (ИП) цифр' : getInnHint(inn)}
                </p>
              )}
            </div>

            {searchError && (
              <div className="flex items-start gap-2 p-3 rounded-lg bg-destructive/10 border border-destructive/20">
                <Icon name="AlertCircle" size={18} className="text-destructive shrink-0 mt-0.5" />
                <p className="text-sm text-destructive">{searchError}</p>
              </div>
            )}

            {foundCompany && (
              <div className="flex items-start gap-3 p-4 rounded-lg bg-primary/10 border border-primary/20 animate-fade-in">
                <Icon name="CheckCircle2" size={20} className="text-primary shrink-0 mt-0.5" />
                <div>
                  <p className="text-xs text-muted-foreground mb-1">Найдена компания</p>
                  <p className="font-semibold text-foreground">{foundCompany.short_name}</p>
                </div>
              </div>
            )}

            <Button
              onClick={handleCreate}
              disabled={!foundCompany || isCreating || limitReached}
              className="w-full h-12 text-base font-semibold"
            >
              {isCreating ? (
                <>
                  <Icon name="Loader2" size={18} className="mr-2 animate-spin" />
                  Создание...
                </>
              ) : 'Создать компанию'}
            </Button>

            {hasCompanies ? (
              <Button variant="ghost" onClick={() => navigate('/app')} className="w-full text-muted-foreground">
                <Icon name="ArrowLeft" size={16} className="mr-2" />
                Вернуться к компаниям
              </Button>
            ) : (
              <Button variant="ghost" onClick={logout} className="w-full text-muted-foreground">
                Выйти из аккаунта
              </Button>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
};

export default CreateCompany;