import { useCallback, useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import { Badge } from '@/components/ui/badge';
import Icon from '@/components/ui/icon';
import { useToast } from '@/hooks/use-toast';
import { useAuth } from '@/contexts/AuthContext';
import { TARIFF_MODULES } from '@/config/modules';
import functionUrls from '../../../backend/func2url.json';
import { discountedYearPrice, fullYearPrice } from '@/lib/tariffPricing';

const api = (functionUrls as Record<string, string>)['tariffs-list'];

interface Tariff {
  id: number;
  slug: string;
  name: string;
  price: number;
  is_active: boolean;
  modules: string[];
  max_companies: number | null;
  max_users: number | null;
  max_integrations: number | null;
  max_automations: number | null;
  period_days: number;
  yearly_discount_percent: number;
  trial_days: number;
  companies_count: number;
}

const LIMITS: { key: 'max_companies' | 'max_users' | 'max_integrations' | 'max_automations'; label: string; icon: string }[] = [
  { key: 'max_companies', label: 'Компании', icon: 'Building2' },
  { key: 'max_users', label: 'Пользователи', icon: 'Users' },
  { key: 'max_integrations', label: 'Интеграции', icon: 'Plug' },
  { key: 'max_automations', label: 'Автоматизации', icon: 'Workflow' }
];

const yearPrice = (t: Tariff) => discountedYearPrice(t.price, t.period_days, t.yearly_discount_percent);

const NumberRow = ({ icon, label, value, unit, onChange }: { icon: string; label: string; value: number; unit: string; onChange: (v: string) => void }) => (
  <div className="flex items-center gap-3 text-sm">
    <Icon name={icon} size={16} className="text-muted-foreground" />
    <span className="flex-1">{label}</span>
    <Input value={String(value)} onChange={(e) => onChange(e.target.value)} className="h-8 w-20 text-right" />
    <span className="w-8 text-xs text-muted-foreground">{unit}</span>
  </div>
);

const TariffCard = ({ tariff, onSave }: { tariff: Tariff; onSave: (t: Tariff) => Promise<boolean> }) => {
  const [draft, setDraft] = useState<Tariff>(tariff);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => setDraft(tariff), [tariff]);

  const changed = JSON.stringify(draft) !== JSON.stringify(tariff);
  const toggleModule = (id: string, on: boolean) =>
    setDraft((d) => ({ ...d, modules: on ? [...d.modules, id] : d.modules.filter((m) => m !== id) }));
  const setLimit = (key: typeof LIMITS[number]['key'], value: string) => {
    const digits = value.replace(/\D/g, '');
    setDraft((d) => ({ ...d, [key]: digits === '' ? null : Number(digits) }));
  };

  const save = async () => {
    setIsSaving(true);
    await onSave(draft);
    setIsSaving(false);
  };

  return (
    <Card className="flex flex-col border-border bg-card">
      <CardHeader className="space-y-3">
        <div className="flex items-center justify-between gap-2">
          <CardTitle className="text-lg">
            <Input
              value={draft.name}
              onChange={(e) => setDraft({ ...draft, name: e.target.value })}
              className="h-9 text-lg font-semibold"
            />
          </CardTitle>
          <label className="flex shrink-0 items-center gap-2 text-xs text-muted-foreground">
            <Switch checked={draft.is_active} onCheckedChange={(v) => setDraft({ ...draft, is_active: v })} />
            {draft.is_active ? 'Активен' : 'Скрыт'}
          </label>
        </div>
        <div className="flex items-center gap-2">
          <Input
            value={String(draft.price)}
            onChange={(e) => setDraft({ ...draft, price: Number(e.target.value.replace(/[^\d.]/g, '')) || 0 })}
            className="h-9 w-32"
          />
          <span className="text-sm text-muted-foreground">₽ / {draft.period_days} дн.</span>
          <Badge variant="outline" className="ml-auto">компаний: {tariff.companies_count}</Badge>
        </div>
      </CardHeader>
      <CardContent className="flex flex-1 flex-col gap-5">
        <div className="space-y-2">
          <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Модули</div>
          {TARIFF_MODULES.map((m) => (
            <label key={m.id} className="flex items-center gap-3 text-sm">
              <Checkbox checked={draft.modules.includes(m.id)} onCheckedChange={(v) => toggleModule(m.id, Boolean(v))} />
              <Icon name={m.icon} size={16} className="text-muted-foreground" />
              {m.name}
            </label>
          ))}
        </div>

        <div className="space-y-2">
          <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Лимиты</div>
          {LIMITS.map((l) => (
            <div key={l.key} className="flex items-center gap-3 text-sm">
              <Icon name={l.icon} size={16} className="text-muted-foreground" />
              <span className="flex-1">{l.label}</span>
              <Input
                value={draft[l.key] ?? ''}
                placeholder="∞"
                onChange={(e) => setLimit(l.key, e.target.value)}
                className="h-8 w-20 text-right"
              />
            </div>
          ))}
          <p className="text-xs text-muted-foreground">Пустое поле — без ограничения</p>
        </div>

        <div className="space-y-2">
          <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Срок и оплата</div>
          <NumberRow
            icon="CalendarDays"
            label="Срок действия"
            value={draft.period_days}
            unit="дн."
            onChange={(v) => setDraft({ ...draft, period_days: Number(v.replace(/\D/g, '')) || 0 })}
          />
          <NumberRow
            icon="Gift"
            label="Пробный период"
            value={draft.trial_days}
            unit="дн."
            onChange={(v) => setDraft({ ...draft, trial_days: Math.min(365, Number(v.replace(/\D/g, '')) || 0) })}
          />
          <NumberRow
            icon="Percent"
            label="Скидка при оплате за год"
            value={draft.yearly_discount_percent}
            unit="%"
            onChange={(v) => setDraft({ ...draft, yearly_discount_percent: Math.min(99, Number(v.replace(/[^\d.]/g, '')) || 0) })}
          />
          <p className="text-xs text-muted-foreground">
            {draft.trial_days > 0 ? `Пробный период: ${draft.trial_days} дн. бесплатно. ` : 'Без пробного периода. '}
            За год: {yearPrice(draft).toLocaleString('ru-RU')} ₽
            {draft.yearly_discount_percent > 0 && ` вместо ${Math.round(fullYearPrice(draft.price, draft.period_days)).toLocaleString('ru-RU')} ₽`}
          </p>
        </div>

        <Button className="mt-auto" onClick={save} disabled={!changed || isSaving}>
          {isSaving ? 'Сохранение...' : 'Сохранить'}
        </Button>
      </CardContent>
    </Card>
  );
};

const AdminTariffsSection = () => {
  const { user } = useAuth();
  const { toast } = useToast();
  const [tariffs, setTariffs] = useState<Tariff[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!user) return;
    const res = await fetch(`${api}?requester_user_id=${user.user_id}`);
    const data = await res.json();
    if (res.ok) setTariffs(data.tariffs);
    else setError(data.error || 'Не удалось загрузить тарифы');
  }, [user]);

  useEffect(() => {
    load();
  }, [load]);

  const save = async (t: Tariff) => {
    const res = await fetch(api, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'save', requester_user_id: user?.user_id, ...t })
    });
    const data = await res.json();
    if (res.ok) {
      setTariffs(data.tariffs);
      toast({ title: `Тариф «${t.name}» сохранён`, description: 'Клиенты увидят изменения после обновления страницы' });
      return true;
    }
    toast({ title: 'Ошибка', description: data.error, variant: 'destructive' });
    return false;
  };

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h2 className="text-3xl font-display font-bold text-foreground mb-2">Тарифы</h2>
        <p className="text-muted-foreground">
          Разделы и лимиты тарифа. Сотрудник видит раздел, только если он есть и в тарифе компании, и в его роли.
        </p>
      </div>
      {error && <div className="text-destructive">{error}</div>}
      {!tariffs && !error && (
        <div className="flex h-64 items-center justify-center">
          <Icon name="Loader2" size={28} className="animate-spin text-muted-foreground" />
        </div>
      )}
      {tariffs && (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
          {tariffs.map((t) => (
            <TariffCard key={t.id} tariff={t} onSave={save} />
          ))}
        </div>
      )}
    </div>
  );
};

export default AdminTariffsSection;
