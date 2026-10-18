import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import Icon from '@/components/ui/icon';
import { ConfigState } from './providerFieldsConfig';
import functionUrls from '../../../backend/func2url.json';

interface PaymentType {
  id: number;
  name: string;
}

interface MoyklassPaymentTypesPickerProps {
  companyId: number;
  integrationId?: number;
  config: ConfigState;
  onConfigChange: (config: ConfigState) => void;
}

const api = (functionUrls as Record<string, string>)['crm-fields'];

const MoyklassPaymentTypesPicker = ({ companyId, integrationId, config, onConfigChange }: MoyklassPaymentTypesPickerProps) => {
  const [types, setTypes] = useState<PaymentType[] | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');

  const selected = Array.isArray(config.payment_type_ids) ? (config.payment_type_ids as string[]) : [];
  const apiKey = String(config.api_key ?? '').trim();

  const load = async () => {
    setIsLoading(true);
    setError('');
    try {
      const res = await fetch(api, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'moyklass_payment_types', company_id: companyId, api_key: apiKey || undefined, integration_id: apiKey ? undefined : integrationId })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Не удалось получить способы оплаты');
      setTypes(data.payment_types || []);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось получить способы оплаты');
    } finally {
      setIsLoading(false);
    }
  };

  const toggle = (id: number) => {
    const v = String(id);
    onConfigChange({ ...config, payment_type_ids: selected.includes(v) ? selected.filter((x) => x !== v) : [...selected, v] });
  };

  return (
    <div className="space-y-2">
      <Label>Способы оплаты, по которым создавать чеки</Label>
      <p className="text-xs text-muted-foreground">
        Не выбрано ничего — чеки по всем платежам. Если онлайн-оплаты уже пробивает касса, подключённая к «Мой Класс»,
        выберите только остальные (например, наличные и переводы), иначе чеки задвоятся.
      </p>

      {types === null ? (
        <div className="space-y-2">
          {selected.length > 0 && (
            <p className="text-sm">Выбрано способов: {selected.length}</p>
          )}
          <Button type="button" variant="outline" size="sm" onClick={load} disabled={isLoading || (!apiKey && !integrationId)}>
            <Icon name={isLoading ? 'Loader2' : 'ListChecks'} size={14} className={`mr-2 ${isLoading ? 'animate-spin' : ''}`} />
            {selected.length > 0 ? 'Изменить способы оплаты' : 'Загрузить способы оплаты'}
          </Button>
          {!apiKey && !integrationId && <p className="text-xs text-muted-foreground">Сначала укажите ключ API.</p>}
        </div>
      ) : types.length === 0 ? (
        <p className="text-sm text-muted-foreground">В «Мой Класс» нет способов оплаты.</p>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          {types.map((t) => (
            <label key={t.id} className="flex items-center gap-2 rounded-md border border-border px-3 py-2 cursor-pointer hover:bg-muted/40">
              <input type="checkbox" checked={selected.includes(String(t.id))} onChange={() => toggle(t.id)} />
              <span className="text-sm">{t.name}</span>
            </label>
          ))}
        </div>
      )}

      {error && (
        <div className="flex items-start gap-2 text-xs text-destructive">
          <Icon name="CircleAlert" size={14} className="mt-0.5 shrink-0" />
          {error}
        </div>
      )}
    </div>
  );
};

export default MoyklassPaymentTypesPicker;
