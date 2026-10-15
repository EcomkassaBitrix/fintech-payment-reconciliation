import { Fragment, useCallback, useEffect, useState } from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import Icon from '@/components/ui/icon';
import { useToast } from '@/hooks/use-toast';
import { useAuth } from '@/contexts/AuthContext';
import { formatShortDate } from '@/lib/subscription';
import functionUrls from '../../../backend/func2url.json';
import CouponDialog, { Coupon, CouponTariff } from './CouponDialog';

const api = (functionUrls as Record<string, string>)['admin-tariffs'];

interface Activation {
  id: number;
  company_name: string;
  inn: string | null;
  created_at: string;
  period_end: string | null;
}

const todayIso = () => new Date().toISOString().slice(0, 10);

const couponState = (c: Coupon) => {
  if (!c.is_active) return { label: 'Выключен', className: 'border-border text-muted-foreground' };
  if (c.valid_until < todayIso()) return { label: 'Истёк', className: 'border-border text-muted-foreground' };
  if (c.usage_type === 'single' && (c.activations || 0) > 0)
    return { label: 'Использован', className: 'border-border text-muted-foreground' };
  return { label: 'Действует', className: 'border-primary/40 bg-primary/10 text-primary' };
};

const AdminCouponsSection = () => {
  const { user } = useAuth();
  const { toast } = useToast();
  const [coupons, setCoupons] = useState<Coupon[] | null>(null);
  const [tariffs, setTariffs] = useState<CouponTariff[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<Coupon | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [openId, setOpenId] = useState<number | null>(null);
  const [activations, setActivations] = useState<Activation[] | null>(null);

  const load = useCallback(async () => {
    if (!user) return;
    const res = await fetch(`${api}?view=coupons&requester_user_id=${user.user_id}`);
    const data = await res.json();
    if (res.ok) {
      setCoupons(data.coupons);
      setTariffs(data.tariffs);
    } else setError(data.error || 'Не удалось загрузить купоны');
  }, [user]);

  useEffect(() => {
    load();
  }, [load]);

  const save = async (c: Coupon) => {
    const res = await fetch(api, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'coupon_save', requester_user_id: user?.user_id, ...c })
    });
    const data = await res.json();
    if (res.ok) {
      setCoupons(data.coupons);
      toast({ title: `Купон ${c.code} сохранён` });
      return true;
    }
    toast({ title: 'Ошибка', description: data.error, variant: 'destructive' });
    return false;
  };

  const copyCode = async (code: string) => {
    try {
      await navigator.clipboard.writeText(code);
      toast({ title: `Промокод ${code} скопирован` });
    } catch {
      toast({ title: 'Не удалось скопировать', variant: 'destructive' });
    }
  };

  const toggleActivations = async (id: number) => {
    if (openId === id) {
      setOpenId(null);
      return;
    }
    setOpenId(id);
    setActivations(null);
    const res = await fetch(`${api}?view=coupon_activations&coupon_id=${id}&requester_user_id=${user?.user_id}`);
    const data = await res.json();
    setActivations(res.ok ? data.activations : []);
  };

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="mb-2 text-3xl font-display font-bold text-foreground">Купоны</h2>
          <p className="text-muted-foreground">Промокоды, которые бесплатно включают тариф на месяц или год</p>
        </div>
        <Button
          onClick={() => {
            setEditing(null);
            setDialogOpen(true);
          }}
        >
          <Icon name="Plus" size={16} className="mr-2" />
          Создать купон
        </Button>
      </div>

      {error && <div className="text-destructive">{error}</div>}
      {!coupons && !error && (
        <div className="flex h-64 items-center justify-center">
          <Icon name="Loader2" size={28} className="animate-spin text-muted-foreground" />
        </div>
      )}

      {coupons && (
        <Card>
          <CardContent className="p-0">
            {coupons.length === 0 ? (
              <div className="p-10 text-center text-sm text-muted-foreground">Купонов пока нет</div>
            ) : (
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Промокод</TableHead>
                      <TableHead>Тариф</TableHead>
                      <TableHead>Срок</TableHead>
                      <TableHead>Тип</TableHead>
                      <TableHead>Применить до</TableHead>
                      <TableHead>Применений</TableHead>
                      <TableHead>Статус</TableHead>
                      <TableHead />
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {coupons.map((c) => {
                      const st = couponState(c);
                      return (
                        <Fragment key={c.id}>
                          <TableRow>
                            <TableCell className="font-mono font-semibold">
                              <div className="group flex items-center gap-1.5">
                                {c.code}
                                <button
                                  type="button"
                                  title="Скопировать"
                                  className="rounded p-1 text-muted-foreground opacity-0 transition-opacity hover:bg-muted hover:text-foreground focus:opacity-100 group-hover:opacity-100"
                                  onClick={() => copyCode(c.code)}
                                >
                                  <Icon name="Copy" size={14} />
                                </button>
                              </div>
                            </TableCell>
                            <TableCell>{c.tariff_name}</TableCell>
                            <TableCell>{c.period === 'year' ? '1 год' : '1 месяц'}</TableCell>
                            <TableCell>{c.usage_type === 'single' ? 'Одноразовый' : 'Многоразовый'}</TableCell>
                            <TableCell>{formatShortDate(c.valid_until)}</TableCell>
                            <TableCell>
                              <button
                                className="flex items-center gap-1 text-primary hover:underline disabled:text-muted-foreground disabled:no-underline"
                                disabled={!c.activations}
                                onClick={() => c.id && toggleActivations(c.id)}
                              >
                                {c.activations || 0}
                                {Boolean(c.activations) && (
                                  <Icon name={openId === c.id ? 'ChevronUp' : 'ChevronDown'} size={14} />
                                )}
                              </button>
                            </TableCell>
                            <TableCell>
                              <Badge variant="outline" className={st.className}>
                                {st.label}
                              </Badge>
                            </TableCell>
                            <TableCell className="text-right">
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => {
                                  setEditing(c);
                                  setDialogOpen(true);
                                }}
                              >
                                <Icon name="Pencil" size={14} />
                              </Button>
                            </TableCell>
                          </TableRow>
                          {openId === c.id && (
                            <TableRow>
                              <TableCell colSpan={8} className="bg-muted/40">
                                {!activations ? (
                                  <Icon name="Loader2" size={16} className="animate-spin text-muted-foreground" />
                                ) : (
                                  <div className="space-y-1 text-sm">
                                    {activations.map((a) => (
                                      <div key={a.id} className="flex flex-wrap gap-x-3">
                                        <span className="font-medium text-foreground">{a.company_name}</span>
                                        {a.inn && <span className="text-muted-foreground">ИНН {a.inn}</span>}
                                        <span className="text-muted-foreground">применил {formatShortDate(a.created_at)}</span>
                                        {a.period_end && (
                                          <span className="text-muted-foreground">· подписка до {formatShortDate(a.period_end)}</span>
                                        )}
                                      </div>
                                    ))}
                                  </div>
                                )}
                              </TableCell>
                            </TableRow>
                          )}
                        </Fragment>
                      );
                    })}
                  </TableBody>
                </Table>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      <CouponDialog
        open={dialogOpen}
        coupon={editing}
        tariffs={tariffs}
        onClose={() => setDialogOpen(false)}
        onSave={save}
      />
    </div>
  );
};

export default AdminCouponsSection;