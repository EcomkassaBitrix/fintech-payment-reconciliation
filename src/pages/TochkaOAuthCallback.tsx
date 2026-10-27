import { useEffect, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from "@/lib/router-compat";
import { Button } from '@/components/ui/button';
import Icon from '@/components/ui/icon';
import { useAuth } from '@/contexts/AuthContext';
import functionUrls from '../../backend/func2url.json';

const TochkaOAuthCallback = () => {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const { user, isLoading, setCurrentCompanyId } = useAuth();
  const [error, setError] = useState('');
  const started = useRef(false);

  useEffect(() => {
    if (isLoading || started.current) return;
    if (!user) {
      setError('Сессия истекла — войдите и подключите Точку ещё раз');
      return;
    }
    started.current = true;

    const code = params.get('code');
    const companyId = Number(params.get('state'));
    const bankError = params.get('error_description') || params.get('error');
    if (bankError || !code || !companyId) {
      setError(bankError ? `Точка: ${bankError}` : 'Доступ не подтверждён — попробуйте подключить ещё раз');
      return;
    }

    fetch(functionUrls['tochka-oauth'], {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code, company_id: companyId })
    })
      .then((r) => r.json())
      .then((data) => {
        if (!data.success) {
          setError(data.error || 'Не удалось подключить Точку');
          return;
        }
        setCurrentCompanyId(companyId);
        navigate('/app?section=integrations', { replace: true });
      })
      .catch(() => setError('Проблема с подключением к серверу'));
  }, [isLoading, user, params, navigate, setCurrentCompanyId]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-background p-4">
      <div className="max-w-sm w-full text-center space-y-4">
        {error ? (
          <>
            <Icon name="CircleAlert" size={40} className="mx-auto text-destructive" />
            <p className="text-sm text-foreground">{error}</p>
            <Button onClick={() => navigate(user ? '/app?section=integrations' : '/login', { replace: true })}>
              {user ? 'Вернуться к интеграциям' : 'Войти'}
            </Button>
          </>
        ) : (
          <>
            <Icon name="Loader2" size={40} className="mx-auto animate-spin text-primary" />
            <p className="text-sm text-muted-foreground">Подключаем счёт Точки…</p>
          </>
        )}
      </div>
    </div>
  );
};

export default TochkaOAuthCallback;