import { useEffect, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import Icon from '@/components/ui/icon';
import { useAuth } from '@/contexts/AuthContext';
import functionUrls from '../../backend/func2url.json';

const YOOKASSA_ERRORS: Record<string, string> = {
  access_denied: 'Вы отказали в доступе — магазин не подключён',
  invalid_request: 'Некорректный запрос — попробуйте подключить ещё раз',
  invalid_scope: 'Приложению не хватает прав — напишите в поддержку Сверки',
  server_error: 'ЮKassa временно недоступна — попробуйте позже',
  temporarily_unavailable: 'ЮKassa временно недоступна — попробуйте позже'
};

const YookassaOAuthCallback = () => {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const { user, isLoading, setCurrentCompanyId } = useAuth();
  const [error, setError] = useState('');
  const started = useRef(false);

  useEffect(() => {
    if (isLoading || started.current) return;
    if (!user) {
      setError('Сессия истекла — войдите и подключите ЮKassa ещё раз');
      return;
    }
    started.current = true;

    const code = params.get('code');
    const companyId = Number(params.get('state'));
    const kassaError = params.get('error');
    if (kassaError || !code || !companyId) {
      setError(
        kassaError
          ? YOOKASSA_ERRORS[kassaError] || `ЮKassa: ${params.get('error_description') || kassaError}`
          : 'Доступ не подтверждён — попробуйте подключить ещё раз'
      );
      return;
    }

    fetch(`${functionUrls['tochka-oauth']}?provider=yookassa`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code, company_id: companyId })
    })
      .then((r) => r.json())
      .then((data) => {
        if (!data.success) {
          setError(data.error || 'Не удалось подключить ЮKassa');
          return;
        }
        setCurrentCompanyId(companyId);
        navigate('/app?section=integrations&yookassa=connected', { replace: true });
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
            <p className="text-sm text-muted-foreground">Подключаем магазин ЮKassa…</p>
          </>
        )}
      </div>
    </div>
  );
};

export default YookassaOAuthCallback;
