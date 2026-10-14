import { useState } from 'react';
import { Button } from '@/components/ui/button';
import Icon from '@/components/ui/icon';
import { useToast } from '@/hooks/use-toast';
import functionUrls from '../../../backend/func2url.json';
import { UserIntegration } from './integrationsPageTypes';

interface Props {
  items: UserIntegration[];
  companyId: number;
  formatDate: (dateStr: string | null) => string;
  onRestored: () => void;
}

const HiddenIntegrationsBlock = ({ items, companyId, formatDate, onRestored }: Props) => {
  const [busy, setBusy] = useState<number | null>(null);
  const { toast } = useToast();
  if (items.length === 0) return null;

  const restore = async (item: UserIntegration) => {
    setBusy(item.id);
    try {
      const res = await fetch(functionUrls['integrations-update'], {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'restore_hidden', integration_id: item.id, company_id: companyId })
      });
      const data = await res.json().catch(() => ({}));
      if (res.ok && data.success) {
        toast({
          title: `Интеграция «${item.integration_name}» восстановлена`,
          description: data.restored_scenarios ? `Вернули сценариев: ${data.restored_scenarios}` : undefined
        });
        onRestored();
      } else {
        toast({ title: 'Не удалось восстановить', description: data.error, variant: 'destructive' });
      }
    } catch {
      toast({ title: 'Ошибка подключения', variant: 'destructive' });
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="rounded-xl border border-dashed border-warning/50 bg-warning/5 p-4">
      <div className="mb-1 flex items-center gap-2 font-semibold">
        <Icon name="EyeOff" size={18} className="text-warning" />
        Скрыты при переходе на тариф ниже
      </div>
      <p className="mb-3 text-sm text-muted-foreground">
        Видно только администратору платформы. Клиент их не видит, они не работают. Настройки и история сохранены.
      </p>
      <div className="space-y-2">
        {items.map((item) => (
          <div key={item.id} className="flex flex-wrap items-center gap-3 rounded-lg border border-border bg-card p-3">
            <div className="min-w-0 flex-1">
              <div className="truncate font-medium">{item.integration_name}</div>
              <div className="text-xs text-muted-foreground">
                {item.provider_name} · скрыта {formatDate(item.hidden_at || null)}
              </div>
            </div>
            <Button size="sm" variant="outline" disabled={busy === item.id} onClick={() => restore(item)}>
              <Icon name={busy === item.id ? 'Loader2' : 'RotateCcw'} size={14} className={`mr-2 ${busy === item.id ? 'animate-spin' : ''}`} />
              Восстановить
            </Button>
          </div>
        ))}
      </div>
    </div>
  );
};

export default HiddenIntegrationsBlock;
