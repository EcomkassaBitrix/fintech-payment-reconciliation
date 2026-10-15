import { useEffect, useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Textarea } from '@/components/ui/textarea';
import Icon from '@/components/ui/icon';
import { Badge } from '@/components/ui/badge';
import { useToast } from '@/hooks/use-toast';
import { useAuth } from '@/contexts/AuthContext';
import functionUrls from '../../../backend/func2url.json';

const api = (functionUrls as Record<string, string>)['platform-settings'];

interface MaintenanceCardProps {
  enabled: boolean;
  message: string | null;
  until: string | null;
  onSaved: () => void;
}

const toLocalInput = (iso: string | null) => {
  if (!iso) return '';
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
};

const MaintenanceCard = ({ enabled, message, until, onSaved }: MaintenanceCardProps) => {
  const { user } = useAuth();
  const { toast } = useToast();
  const [isOn, setIsOn] = useState(enabled);
  const [text, setText] = useState(message || '');
  const [untilLocal, setUntilLocal] = useState(toLocalInput(until));
  const [isSaving, setIsSaving] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    setIsOn(enabled);
    setText(message || '');
    setUntilLocal(toLocalInput(until));
  }, [enabled, message, until]);

  const save = async () => {
    if (!user) return;
    setIsSaving(true);
    try {
      const res = await fetch(api, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action: 'save_maintenance',
          requester_user_id: user.user_id,
          maintenance_enabled: isOn,
          maintenance_message: text,
          maintenance_until: untilLocal ? new Date(untilLocal).toISOString() : null
        })
      });
      const data = await res.json();
      if (res.ok) {
        onSaved();
        toast({
          title: isOn ? 'Режим техработ включён' : 'Режим техработ выключен',
          description: isOn ? 'Клиенты увидят заглушку при следующем открытии сайта. Администраторам сайт доступен' : 'Сайт снова открыт для всех'
        });
      } else {
        toast({ title: 'Ошибка', description: data.error, variant: 'destructive' });
      }
    } finally {
      setIsSaving(false);
    }
  };

  const changed = isOn !== enabled || text !== (message || '') || untilLocal !== toLocalInput(until);

  return (
    <Card className={`bg-card ${isOn ? 'border-warning/60' : 'border-border'}`}>
      <CardHeader className="p-0">
        <button
          type="button"
          onClick={() => setOpen(!open)}
          className="flex w-full items-start gap-3 rounded-lg px-5 py-4 text-left transition-colors hover:bg-muted/40"
        >
          <Icon name={open ? 'ChevronDown' : 'ChevronRight'} size={18} className="mt-1 shrink-0 text-muted-foreground" />
          <div className="min-w-0 flex-1 space-y-1.5">
            <CardTitle className="flex flex-wrap items-center gap-2">
              <Icon name="Construction" fallback="Wrench" size={20} />
              Технические работы
              {enabled && (
                <Badge variant="outline" className="border-warning/40 bg-warning/10 text-warning">
                  Сайт закрыт
                </Badge>
              )}
            </CardTitle>
            <CardDescription>
              Закрывает сайт заглушкой «Сайт временно недоступен» для всех, кроме администраторов платформы.
              Приём платежей, вебхуков и фоновые задачи продолжают работать
            </CardDescription>
          </div>
        </button>
      </CardHeader>
      {open && (
      <CardContent className="space-y-4 pt-2">
        <div className="flex items-center justify-between gap-3 rounded-lg border border-border p-3">
          <div>
            <div className="text-sm font-medium">Показывать заглушку</div>
            <div className="text-xs text-muted-foreground">{isOn ? 'Сейчас сайт закрыт для клиентов' : 'Сайт открыт'}</div>
          </div>
          <Switch checked={isOn} onCheckedChange={setIsOn} />
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="maintenance_message">Текст для клиентов</Label>
          <Textarea
            id="maintenance_message"
            value={text}
            maxLength={500}
            placeholder="Мы обновляем сервис, чтобы сверка работала ещё быстрее. Это ненадолго."
            onChange={(e) => setText(e.target.value)}
          />
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="maintenance_until">Когда вернёмся (необязательно)</Label>
          <Input
            id="maintenance_until"
            type="datetime-local"
            value={untilLocal}
            onChange={(e) => setUntilLocal(e.target.value)}
            className="max-w-xs"
          />
        </div>

        <div className="flex flex-wrap gap-2">
          <Button onClick={save} disabled={!changed || isSaving} className="gap-2">
            <Icon name={isSaving ? 'Loader2' : 'Save'} size={16} className={isSaving ? 'animate-spin' : ''} />
            Сохранить
          </Button>
          <Button variant="outline" className="gap-2" onClick={() => window.open('/?maintenance_preview=1', '_blank')}>
            <Icon name="Eye" size={16} />
            Предпросмотр
          </Button>
        </div>
      </CardContent>
      )}
    </Card>
  );
};

export default MaintenanceCard;
