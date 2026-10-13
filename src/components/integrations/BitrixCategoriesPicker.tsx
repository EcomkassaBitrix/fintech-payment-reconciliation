import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import Icon from '@/components/ui/icon';
import { ConfigState, validateBitrixWebhook } from './providerFieldsConfig';
import functionUrls from '../../../backend/func2url.json';

interface Category {
  id: string;
  name: string;
}

interface BitrixCategoriesPickerProps {
  companyId: number;
  integrationId?: number;
  config: ConfigState;
  onConfigChange: (config: ConfigState) => void;
}

const api = (functionUrls as Record<string, string>)['crm-fields'];

const BitrixCategoriesPicker = ({ companyId, integrationId, config, onConfigChange }: BitrixCategoriesPickerProps) => {
  const [categories, setCategories] = useState<Category[] | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');

  const selected = Array.isArray(config.deal_categories) ? (config.deal_categories as string[]) : [];
  const webhook = String(config.webhook_url ?? '').trim();
  const webhookOk = !!webhook && !validateBitrixWebhook(webhook);
  const savedNames: Record<string, string> = Object.fromEntries(
    (Array.isArray(config.deal_category_names) ? (config.deal_category_names as string[]) : [])
      .map((pair) => [pair.split(':')[0], pair.slice(pair.indexOf(':') + 1)])
  );

  const load = async () => {
    setIsLoading(true);
    setError('');
    try {
      const q = new URLSearchParams({ company_id: String(companyId), categories: '1' });
      if (webhookOk) q.set('webhook_url', webhook);
      else if (integrationId) q.set('integration_id', String(integrationId));
      const res = await fetch(`${api}?${q.toString()}`);
      const data = await res.json();
      if (!data.success) throw new Error(data.error || 'Не удалось загрузить воронки');
      setCategories(data.categories || []);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось загрузить воронки');
    } finally {
      setIsLoading(false);
    }
  };

  const toggle = (c: Category) => {
    const next = selected.includes(c.id) ? selected.filter((x) => x !== c.id) : [...selected, c.id];
    const names = (categories || []).filter((x) => next.includes(x.id)).map((x) => `${x.id}:${x.name}`);
    onConfigChange({ ...config, deal_categories: next, deal_category_names: names });
  };

  return (
    <div className="space-y-2">
      <Label>Воронки сделок этой интеграции</Label>
      <p className="text-xs text-muted-foreground">
        Сделки из этих воронок относятся к этой интеграции. Если робот копирует сделку со ссылкой на оплату в другую
        воронку, к чеку берём сделку из выбранной здесь, а копии не загружаем
      </p>

      {categories === null ? (
        <div className="space-y-2">
          {selected.length > 0 && (
            <p className="text-sm">
              Выбрано: {selected.map((id) => savedNames[id] || `Воронка ${id}`).join(', ')}
            </p>
          )}
          <Button type="button" variant="outline" size="sm" onClick={load} disabled={isLoading || (!webhookOk && !integrationId)}>
            <Icon name={isLoading ? 'Loader2' : 'Filter'} size={14} className={`mr-2 ${isLoading ? 'animate-spin' : ''}`} />
            {selected.length > 0 ? 'Изменить воронки' : 'Загрузить воронки'}
          </Button>
          {!webhookOk && !integrationId && <p className="text-xs text-muted-foreground">Сначала укажите входящий вебхук.</p>}
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          {categories.map((c) => (
            <label key={c.id} className="flex items-center gap-2 rounded-md border border-border px-3 py-2 cursor-pointer hover:bg-muted/40">
              <input type="checkbox" checked={selected.includes(c.id)} onChange={() => toggle(c)} />
              <span className="text-sm">{c.name}</span>
            </label>
          ))}
        </div>
      )}
      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  );
};

export default BitrixCategoriesPicker;
