import { useEffect, useState } from 'react';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import Icon from '@/components/ui/icon';
import { Switch } from '@/components/ui/switch';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

export interface Coupon {
  id?: number;
  code: string;
  tariff_id: number | null;
  tariff_name?: string;
  period: 'month' | 'year';
  usage_type: 'single' | 'multi';
  valid_until: string;
  is_active: boolean;
  activations?: number;
}

export interface CouponTariff {
  id: number;
  name: string;
  is_active: boolean;
}

interface Props {
  open: boolean;
  coupon: Coupon | null;
  tariffs: CouponTariff[];
  onClose: () => void;
  onSave: (c: Coupon) => Promise<boolean>;
}

const CODE_ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';

const randomCode = () => {
  const bytes = new Uint8Array(8);
  crypto.getRandomValues(bytes);
  const chars = Array.from(bytes, (b) => CODE_ALPHABET[b % CODE_ALPHABET.length]).join('');
  return `${chars.slice(0, 4)}-${chars.slice(4)}`;
};

const inMonth = () => {
  const d = new Date();
  d.setMonth(d.getMonth() + 1);
  return d.toISOString().slice(0, 10);
};

const empty = (): Coupon => ({
  code: '',
  tariff_id: null,
  period: 'month',
  usage_type: 'single',
  valid_until: inMonth(),
  is_active: true
});

const CouponDialog = ({ open, coupon, tariffs, onClose, onSave }: Props) => {
  const [form, setForm] = useState<Coupon>(empty());
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (open) setForm(coupon ? { ...coupon } : empty());
  }, [open, coupon]);

  const set = <K extends keyof Coupon>(k: K, v: Coupon[K]) => setForm((f) => ({ ...f, [k]: v }));
  const valid = form.code.trim() && form.tariff_id && form.valid_until;

  const submit = async () => {
    setSaving(true);
    const ok = await onSave({ ...form, code: form.code.trim().toUpperCase() });
    setSaving(false);
    if (ok) onClose();
  };

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{coupon?.id ? 'Купон' : 'Новый купон'}</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label>Название (промокод)</Label>
            <div className="flex gap-2">
              <Input
                value={form.code}
                placeholder="Например, START2026"
                onChange={(e) => set('code', e.target.value.toUpperCase().replace(/[^A-ZА-ЯЁ0-9_-]/g, ''))}
              />
              <Button type="button" variant="outline" className="shrink-0 gap-2" onClick={() => set('code', randomCode())}>
                <Icon name="Shuffle" size={16} />
                Придумать
              </Button>
            </div>
          </div>
          <div className="space-y-1.5">
            <Label>Тариф</Label>
            <Select value={form.tariff_id ? String(form.tariff_id) : ''} onValueChange={(v) => set('tariff_id', Number(v))}>
              <SelectTrigger>
                <SelectValue placeholder="Выберите тариф" />
              </SelectTrigger>
              <SelectContent>
                {tariffs.map((t) => (
                  <SelectItem key={t.id} value={String(t.id)}>
                    {t.name}
                    {!t.is_active ? ' (выключен)' : ''}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label>Срок подписки</Label>
              <Select value={form.period} onValueChange={(v) => set('period', v as Coupon['period'])}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="month">1 месяц</SelectItem>
                  <SelectItem value="year">1 год</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>Тип</Label>
              <Select value={form.usage_type} onValueChange={(v) => set('usage_type', v as Coupon['usage_type'])}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="single">Одноразовый</SelectItem>
                  <SelectItem value="multi">Многоразовый</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="space-y-1.5">
            <Label>Применить до (включительно)</Label>
            <Input type="date" value={form.valid_until} onChange={(e) => set('valid_until', e.target.value)} />
          </div>
          <p className="text-xs text-muted-foreground">
            {form.usage_type === 'single'
              ? 'Одноразовый — применяет только одна компания.'
              : 'Многоразовый — может применить любая компания, каждая по одному разу.'}
          </p>
          <div className="flex items-center justify-between rounded-lg border border-border px-3 py-2">
            <span className="text-sm">Купон активен</span>
            <Switch checked={form.is_active} onCheckedChange={(v) => set('is_active', v)} />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Отмена
          </Button>
          <Button onClick={submit} disabled={!valid || saving}>
            {saving ? 'Сохраняю…' : 'Сохранить'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default CouponDialog;