import { useState, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import Icon from '@/components/ui/icon';
import functionUrls from '../../../backend/func2url.json';

interface TbankAccount {
  account_number: string;
  currency: string;
  balance: number | null;
}

interface TbankAccountPickerProps {
  companyId: number;
  accountNumber: string;
  onAccountNumberChange: (value: string) => void;
}

const TbankAccountPicker = ({ companyId, accountNumber, onAccountNumberChange }: TbankAccountPickerProps) => {
  const [isChecking, setIsChecking] = useState(true);
  const [isConnected, setIsConnected] = useState(false);
  const [companyName, setCompanyName] = useState('');
  const [isSandbox, setIsSandbox] = useState(false);
  const [accounts, setAccounts] = useState<TbankAccount[]>([]);
  const [isConnecting, setIsConnecting] = useState(false);
  const [tokenInput, setTokenInput] = useState('');
  const [tokenError, setTokenError] = useState('');
  const [isSavingToken, setIsSavingToken] = useState(false);
  const [showToken, setShowToken] = useState(false);

  const checkConnection = async () => {
    setIsChecking(true);
    try {
      const response = await fetch(`${functionUrls['tbank-accounts-list']}?company_id=${companyId}`);
      const data = await response.json();

      if (response.ok) {
        setIsConnected(!!data.is_connected);
        setCompanyName(data.company_name || '');
        setIsSandbox(!!data.sandbox);
        setAccounts(data.accounts || []);
      }
    } catch {
      setIsConnected(false);
    } finally {
      setIsChecking(false);
    }
  };

  useEffect(() => {
    checkConnection();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [companyId]);

  const postAction = async (payload: Record<string, unknown>) => {
    const response = await fetch(functionUrls['tbank-oauth-callback'], {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ company_id: companyId, ...payload })
    });
    return response.json();
  };

  const handleSaveToken = async () => {
    if (!tokenInput.trim()) {
      setTokenError('Вставьте токен из Т-Бизнес');
      return;
    }
    setIsSavingToken(true);
    setTokenError('');
    try {
      const data = await postAction({ action: 'save_token', token: tokenInput.trim() });
      if (data.success) {
        setTokenInput('');
        onAccountNumberChange('');
        await checkConnection();
      } else {
        setTokenError(data.error || 'Не удалось подключить токен');
      }
    } catch {
      setTokenError('Не удалось связаться с сервером, попробуйте ещё раз');
    } finally {
      setIsSavingToken(false);
    }
  };

  const handleDisconnect = async () => {
    setIsConnecting(true);
    try {
      await postAction({ action: 'disconnect' });
      onAccountNumberChange('');
      await checkConnection();
    } finally {
      setIsConnecting(false);
    }
  };

  const methodPicker = (
    <div>
      <Label>Способ подключения</Label>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mt-1.5">
        <div className="flex items-center gap-2 p-3 rounded-lg border border-primary bg-primary/5 text-left">
          <Icon name="KeyRound" size={16} className="text-primary" />
          <div>
            <div className="text-sm font-medium">Токен</div>
            <div className="text-xs text-muted-foreground">Доступно сейчас</div>
          </div>
        </div>
        <div
          aria-disabled="true"
          title="Партнёрская интеграция с Т-Банком скоро будет доступна"
          className="flex items-center gap-2 p-3 rounded-lg border border-border text-left opacity-60 cursor-not-allowed"
        >
          <Icon name="Lock" size={16} className="text-muted-foreground" />
          <div className="min-w-0">
            <div className="text-sm font-medium flex items-center gap-1.5">
              Партнёрская интеграция
              <span className="text-[10px] uppercase tracking-wide rounded-full border border-border px-1.5 py-px text-muted-foreground">
                Скоро
              </span>
            </div>
            <div className="text-xs text-muted-foreground">Вход через Т-Бизнес без токена</div>
          </div>
        </div>
      </div>
    </div>
  );

  const tokenForm = (
    <div className="space-y-1.5">
      <Label htmlFor="tbank_token">Токен Т-Бизнес</Label>
      <div className="flex gap-2">
        <div className="relative flex-1">
          <Input
            id="tbank_token"
            type={showToken ? 'text' : 'password'}
            autoComplete="off"
            placeholder="Вставьте токен"
            value={tokenInput}
            onChange={(e) => { setTokenInput(e.target.value); setTokenError(''); }}
            onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); handleSaveToken(); } }}
            className="pr-10"
          />
          <button
            type="button"
            onClick={() => setShowToken((v) => !v)}
            className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
            tabIndex={-1}
          >
            <Icon name={showToken ? 'EyeOff' : 'Eye'} size={16} />
          </button>
        </div>
        <Button type="button" onClick={handleSaveToken} disabled={isSavingToken}>
          {isSavingToken && <Icon name="Loader2" size={14} className="animate-spin mr-2" />}
          Подключить
        </Button>
      </div>
      {tokenError && <p className="text-xs text-destructive">{tokenError}</p>}
      <p className="text-xs text-muted-foreground">
        Т-Бизнес → Интеграции → API → выпустить токен с доступом к счетам и выписке. После проверки счета подтянутся списком
      </p>
    </div>
  );

  if (isChecking) {
    return (
      <div>
        <Label>Номер расчётного счёта</Label>
        <div className="h-10 flex items-center text-sm text-muted-foreground">
          <Icon name="Loader2" size={14} className="animate-spin mr-2" />
          Проверяем подключение к Т-Бизнес...
        </div>
      </div>
    );
  }

  if (isConnected) {
    return (
      <div className="space-y-3">
        {methodPicker}
        <div className="space-y-2">
        <Label>Номер расчётного счёта</Label>
        <div className="flex items-center gap-2 text-xs text-success mb-1">
          <Icon name="ShieldCheck" size={14} />
          {isSandbox
            ? `Демо-режим песочницы — счета ${companyName || 'компании'} подтягиваются автоматически`
            : `Токен подключён${companyName ? ` — ${companyName}` : ''}`}
        </div>
        <Select value={accountNumber} onValueChange={onAccountNumberChange}>
          <SelectTrigger>
            <SelectValue placeholder="Выберите счёт из списка" />
          </SelectTrigger>
          <SelectContent>
            {accounts.map((acc) => (
              <SelectItem key={acc.account_number} value={acc.account_number}>
                {acc.account_number} {acc.balance !== null ? `· ${acc.balance.toLocaleString('ru-RU')} ₽` : ''}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        </div>
        {isSandbox ? (
          <div className="space-y-2">
            <p className="text-xs text-muted-foreground">
              Сейчас загружаются тестовые операции банка. Чтобы грузить платежи с вашего счёта, подключите свой токен
            </p>
            {tokenForm}
          </div>
        ) : (
          <button
            type="button"
            onClick={handleDisconnect}
            disabled={isConnecting}
            className="text-xs text-muted-foreground underline hover:text-foreground"
          >
            Отключить токен
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {methodPicker}
      {tokenForm}
    </div>
  );
};

export default TbankAccountPicker;
