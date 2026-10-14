import { useEffect, useState } from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle
} from '@/components/ui/alert-dialog';
import Icon from '@/components/ui/icon';
import { useToast } from '@/hooks/use-toast';
import { formatDateTime } from '@/lib/formatDate';
import functionUrls from '../../../backend/func2url.json';

interface Transaction {
  id: number;
  company_id: number;
  company_name: string;
  company_inn: string | null;
  date: string;
  amount: number;
  provider: string;
  provider_name: string;
  status: string;
  error: string | null;
  tariff_name: string;
  period: string;
  is_recurring: boolean;
  refunded_at: string | null;
  refund_amount: number | null;
  can_refund: boolean;
  is_test?: boolean;
}

const api = `${(functionUrls as Record<string, string>)['tochka-oauth']}?provider=yookassa`;
const PAGE = 50;

const STATUSES: Record<string, { label: string; className: string }> = {
  paid: { label: 'Оплачен', className: 'bg-success/10 text-success border-success/20' },
  pending: { label: 'Ожидает оплаты', className: 'bg-warning/10 text-warning border-warning/20' },
  failed: { label: 'Не прошёл', className: 'bg-destructive/10 text-destructive border-destructive/20' },
  refunded: { label: 'Возвращён', className: 'bg-muted text-muted-foreground border-border' },
  partially_refunded: { label: 'Частично возвращён', className: 'bg-muted text-muted-foreground border-border' },
  canceled: { label: 'Отменён', className: 'bg-muted text-muted-foreground border-border' }
};

const FILTERS = [
  ['', 'Все'],
  ['paid', 'Оплачены'],
  ['failed', 'Не прошли'],
  ['pending', 'Ожидают'],
  ['refunded', 'Возвраты'],
  ['canceled', 'Отменённые']
];

const money = (n: number) => `${new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 }).format(n)} ₽`;

const AdminSubscriptionTransactions = () => {
  const { toast } = useToast();
  const [items, setItems] = useState<Transaction[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState('');
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState('');
  const [offset, setOffset] = useState(0);
  const [confirm, setConfirm] = useState<Transaction | null>(null);
  const [refunding, setRefunding] = useState<number | null>(null);

  useEffect(() => {
    const t = setTimeout(() => {
      setQuery(search);
      setOffset(0);
    }, 400);
    return () => clearTimeout(t);
  }, [search]);

  useEffect(() => {
    setLoading(true);
    const params = new URLSearchParams({ action: 'transactions', limit: String(PAGE), offset: String(offset) });
    if (status) params.set('status', status);
    if (query) params.set('search', query);
    fetch(`${api}&${params}`)
      .then((r) => r.json())
      .then((d) => {
        setItems(d.transactions || []);
        setTotal(d.total || 0);
      })
      .catch(() => undefined)
      .finally(() => setLoading(false));
  }, [status, query, offset]);

  const refund = async (tx: Transaction) => {
    setConfirm(null);
    setRefunding(tx.id);
    try {
      const res = await fetch(api, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'refund', payment_id: tx.id })
      });
      const d = await res.json();
      if (d.success) {
        setItems((prev) => prev.map((x) => (x.id === tx.id ? d.transaction : x)));
        toast({ title: 'Платёж возвращён', description: `${tx.company_name} · ${money(tx.amount)}` });
      } else {
        toast({ title: 'Возврат не прошёл', description: d.error, variant: 'destructive' });
      }
    } catch {
      toast({ title: 'Ошибка подключения', variant: 'destructive' });
    } finally {
      setRefunding(null);
    }
  };

  const refundHint = (tx: Transaction) => {
    if (tx.status === 'refunded') return 'Уже возвращён';
    if (!['paid', 'partially_refunded'].includes(tx.status)) return 'Возвращать нечего — платёж не прошёл';
    if (!tx.can_refund) return `Через «${tx.provider_name}» возврат делается вручную`;
    return 'Вернуть платёж';
  };

  return (
    <div className="mt-10">
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h3 className="text-xl font-display font-semibold text-foreground">Транзакции</h3>
          <p className="text-sm text-muted-foreground">Оплаты подписки всеми клиентами</p>
        </div>
        <div className="relative sm:w-72">
          <Icon name="Search" size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Клиент или ИНН" className="pl-9" />
        </div>
      </div>

      <div className="mb-3 flex flex-wrap gap-2">
        {FILTERS.map(([v, l]) => (
          <Button
            key={v}
            size="sm"
            variant={status === v ? 'default' : 'outline'}
            onClick={() => {
              setStatus(v);
              setOffset(0);
            }}
          >
            {l}
          </Button>
        ))}
      </div>

      <Card className="border-border bg-card">
        <CardContent className="p-0">
          {loading ? (
            <div className="flex h-40 items-center justify-center">
              <Icon name="Loader2" className="animate-spin text-primary" size={24} />
            </div>
          ) : items.length === 0 ? (
            <div className="flex h-40 flex-col items-center justify-center gap-2 text-sm text-muted-foreground">
              <Icon name="Receipt" size={24} />
              Транзакций пока нет
            </div>
          ) : (
            <TooltipProvider>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Клиент</TableHead>
                    <TableHead>Дата списания</TableHead>
                    <TableHead className="text-right">Сумма</TableHead>
                    <TableHead>Провайдер</TableHead>
                    <TableHead>Статус</TableHead>
                    <TableHead className="w-12" />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {items.map((tx) => {
                    const st = STATUSES[tx.status] || { label: tx.status, className: '' };
                    const active = tx.can_refund;
                    return (
                      <TableRow key={tx.id}>
                        <TableCell>
                          <div className="font-medium text-foreground">
                            {tx.company_name}
                            {tx.is_test && <Badge variant="outline" className="ml-2 text-[10px]">тест</Badge>}
                          </div>
                          <div className="text-xs text-muted-foreground">
                            {tx.tariff_name} · {tx.period === 'year' ? 'год' : 'месяц'}
                            {tx.is_recurring && ' · автопродление'}
                            {tx.company_inn && ` · ИНН ${tx.company_inn}`}
                          </div>
                        </TableCell>
                        <TableCell className="whitespace-nowrap text-sm">{formatDateTime(tx.date)}</TableCell>
                        <TableCell className="whitespace-nowrap text-right font-medium">
                          {money(tx.amount)}
                          {tx.refund_amount !== null && (
                            <div className="text-xs font-normal text-muted-foreground">возврат {money(tx.refund_amount)}</div>
                          )}
                        </TableCell>
                        <TableCell className="text-sm">{tx.provider_name}</TableCell>
                        <TableCell>
                          <Badge variant="outline" className={st.className}>
                            {st.label}
                          </Badge>
                          {tx.status === 'failed' && tx.error && (
                            <div className="mt-1 max-w-[220px] text-xs text-muted-foreground">{tx.error}</div>
                          )}
                        </TableCell>
                        <TableCell>
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <span>
                                <Button
                                  variant="ghost"
                                  size="icon"
                                  disabled={!active || refunding === tx.id}
                                  onClick={() => setConfirm(tx)}
                                  aria-label="Вернуть платёж"
                                >
                                  <Icon
                                    name={refunding === tx.id ? 'Loader2' : 'Undo2'}
                                    size={16}
                                    className={refunding === tx.id ? 'animate-spin' : active ? 'text-destructive' : ''}
                                  />
                                </Button>
                              </span>
                            </TooltipTrigger>
                            <TooltipContent>{refundHint(tx)}</TooltipContent>
                          </Tooltip>
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </TooltipProvider>
          )}
        </CardContent>
      </Card>

      {total > PAGE && (
        <div className="mt-3 flex items-center justify-between text-sm text-muted-foreground">
          <span>
            {offset + 1}–{Math.min(offset + PAGE, total)} из {total}
          </span>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>
              Назад
            </Button>
            <Button variant="outline" size="sm" disabled={offset + PAGE >= total} onClick={() => setOffset(offset + PAGE)}>
              Дальше
            </Button>
          </div>
        </div>
      )}

      <AlertDialog open={Boolean(confirm)} onOpenChange={(o) => !o && setConfirm(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Вернуть платёж?</AlertDialogTitle>
            <AlertDialogDescription>
              {confirm &&
                `${confirm.company_name} получит обратно ${money(confirm.amount)} на карту через ${confirm.provider_name}. ` +
                  'Отменить возврат будет нельзя. Срок подписки клиента не изменится — при необходимости поправьте его в разделе компаний.'}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Отмена</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={() => confirm && refund(confirm)}
            >
              Вернуть
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
};

export default AdminSubscriptionTransactions;
