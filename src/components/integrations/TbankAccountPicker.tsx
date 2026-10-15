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

  const handleConnect = async () => {
    setIsConnecting(true);
    try {
      const response = await fetch(
        `${functionUrls['tbank-oauth-callback']}?action=authorize_url&company_id=${companyId}&redirect_uri=${encodeURIComponent(window.location.href)}`
      );
      const data = await response.json();

      if (data.sandbox) {
        await checkConnection();
      } else if (data.authorize_url) {
        window.location.href = data.authorize_url;
      }
    } finally {
      setIsConnecting(false);
    }
  };

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

  const tokenForm = (
    <div className="space-y-2 rounded-lg border border-border p-3">
      <Label htmlFor="tbank_token">Токен Т-Бизнес</Label>
      <div className="flex gap-2">
        <Input
          id="tbank_token"
          type="password"
          autoComplete="off"
          placeholder="Вставьте токен"
          value={tokenInput}
          onChange={(e) => { setTokenInput(e.target.value); setTokenError(''); }}
        />
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
          Проверяем подтверждение через Т-Бизнес...
        </div>
      </div>
    );
  }

  if (isConnected) {
    return (
      <div className="space-y-2">
        <Label>Номер расчётного счёта</Label>
        <div className="flex items-center gap-2 text-xs text-success mb-1">
          <Icon name="ShieldCheck" size={14} />
          {isSandbox
            ? `Демо-режим песочницы — счета ${companyName || 'компании'} подтягиваются автоматически`
            : `Доступ подтверждён через Т-Бизнес (${companyName})`}
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
        {isSandbox ? (
          <div className="pt-2 space-y-2">
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
      <div>
        <Label htmlFor="account_number">Номер расчётного счёта</Label>
        <Input
          id="account_number"
          placeholder="40702810110011000000"
          value={accountNumber}
          onChange={(e) => onAccountNumberChange(e.target.value)}
        />
        <p className="text-xs text-muted-foreground mt-1">
          Введите вручную или подключите токен Т-Бизнес — тогда счета подтянутся автоматически
        </p>
      </div>
      {tokenForm}
      <Button type="button" variant="ghost" size="sm" onClick={handleConnect} disabled={isConnecting}>
        {isConnecting ? (
          <Icon name="Loader2" size={14} className="animate-spin mr-2" />
        ) : (
          <Icon name="Link" size={14} className="mr-2" />
        )}
        Попробовать на демо-данных
      </Button>
    </div>
  );
};

export default TbankAccountPicker;
