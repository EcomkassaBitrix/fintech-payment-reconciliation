import { useEffect, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from "@/lib/router-compat";
import { Button } from '@/components/ui/button';
import Icon from '@/components/ui/icon';
import { useAuth } from '@/contexts/AuthContext';
import functionUrls from '../../backend/func2url.json';

const YOOKASSA_ERRORS: Record<string, string> = {
  access_denied: 'Вы отказали в доступе — магазин не подключён',
  invalid_request: 'Некорректный запрос — попробуйте подключить ещё раз',
  invalid_scope: 'Приложению не хватает прав — проверьте доступы в настройках приложения ЮKassa',
  server_error: 'ЮKassa временно недоступна — попробуйте позже',
  temporarily_unavailable: 'ЮKassa временно недоступна — попробуйте позже'
};

const YookassaOAuthCallback = () => {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const { user, isLoading } = useAuth();
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
    const kassaError = params.get('error');
    if (kassaError || !code) {
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
      body: JSON.stringify({ code })
    })
      .then((r) => r.json())
      .then((data) => {
        if (!data.success) {
          setError(data.error || 'Не удалось подключить ЮKassa');
          return;
        }
        navigate('/admin?section=payments&yookassa=connected', { replace: true });
      })
      .catch(() => setError('Проблема с подключением к серверу'));
  }, [isLoading, user, params, navigate]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-background p-4">
      <div className="max-w-sm w-full text-center space-y-4">
        {error ? (
          <>
            <Icon name="CircleAlert" size={40} className="mx-auto text-destructive" />
            <p className="text-sm text-foreground">{error}</p>
            <Button onClick={() => navigate(user ? '/admin?section=payments' : '/login', { replace: true })}>
              {user ? 'Вернуться в раздел «Оплата»' : 'Войти'}
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
