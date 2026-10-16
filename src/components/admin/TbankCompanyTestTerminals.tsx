import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import Icon from '@/components/ui/icon';
import { useToast } from '@/hooks/use-toast';
import { formatDateTime } from '@/lib/formatDate';
import functionUrls from '../../../backend/func2url.json';

const api = `${(functionUrls as Record<string, string>)['tochka-oauth']}?provider=yookassa`;

interface CompanyTerminal {
  company_id: number;
  company_name: string;
  terminal_key: string;
  updated_at: string | null;
}

interface CompanyOption {
  id: number;
  name: string;
}

const TbankCompanyTestTerminals = () => {
  const { toast } = useToast();
  const [terminals, setTerminals] = useState<CompanyTerminal[]>([]);
  const [companies, setCompanies] = useState<CompanyOption[]>([]);
  const [companyId, setCompanyId] = useState('');
  const [terminalKey, setTerminalKey] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    fetch(`${api}&action=company_terminals`)
      .then((r) => r.json())
      .then((d) => {
        setTerminals(d.terminals || []);
        setCompanies(d.companies || []);
      })
      .catch(() => undefined);
  }, []);

  const save = async (body: Record<string, unknown>, success: string) => {
    setBusy(true);
    try {
      const res = await fetch(api, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'save_company_terminal', ...body })
      });
      const d = await res.json();
      if (d.success) {
        setTerminals(d.terminals || []);
        setTerminalKey('');
        setPassword('');
        toast({ title: success });
      } else {
        toast({ title: 'Ошибка', description: d.error, variant: 'destructive' });
      }
    } catch {
      toast({ title: 'Ошибка подключения', variant: 'destructive' });
    } finally {
      setBusy(false);
    }
  };

  const edit = (t: CompanyTerminal) => {
    setCompanyId(String(t.company_id));
    setTerminalKey(t.terminal_key);
    setPassword('');
  };

  return (
    <div className="space-y-4 rounded-lg border border-border p-4">
      <div>
        <p className="font-medium text-foreground">Тестовые терминалы компаний</p>
        <p className="text-sm text-muted-foreground">
          Оплата, привязка и отвязка карты в выбранной компании пойдут через её терминал, а не через терминал платформы.
          Нужно для демо-учётки, которую проверяет банк.
        </p>
      </div>

      {terminals.length > 0 && (
        <div className="space-y-2">
          {terminals.map((t) => (
            <div key={t.company_id} className="flex flex-col gap-2 rounded-md bg-muted/40 px-3 py-2 text-sm sm:flex-row sm:items-center sm:justify-between">
              <div>
                <span className="font-medium text-foreground">{t.company_name}</span>
                <span className="text-muted-foreground"> · терминал {t.terminal_key}</span>
                {t.updated_at && <span className="text-muted-foreground"> · {formatDateTime(t.updated_at)}</span>}
              </div>
              <div className="flex gap-2">
                <Button variant="outline" size="sm" disabled={busy} onClick={() => edit(t)}>
                  <Icon name="Pencil" size={14} className="mr-2" />
                  Изменить
                </Button>
                <Button variant="ghost" size="sm" disabled={busy}
                  onClick={() => save({ company_id: t.company_id, terminal_key: '' }, 'Тестовый терминал отключён')}>
                  Отключить
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="grid gap-3 sm:grid-cols-3">
        <div className="space-y-1.5">
          <Label>Компания</Label>
          <Select value={companyId} onValueChange={setCompanyId}>
            <SelectTrigger>
              <SelectValue placeholder="Выберите компанию" />
            </SelectTrigger>
            <SelectContent>
              {companies.map((c) => (
                <SelectItem key={c.id} value={String(c.id)}>{c.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label>TerminalKey</Label>
          <Input value={terminalKey} onChange={(e) => setTerminalKey(e.target.value.trim())} placeholder="1234567890DEMO" />
        </div>
        <div className="space-y-1.5">
          <Label>Пароль терминала</Label>
          <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
            placeholder={terminals.some((t) => String(t.company_id) === companyId && t.terminal_key === terminalKey) ? 'Оставьте пустым — не менять' : ''} />
        </div>
      </div>
      <Button disabled={busy || !companyId || !terminalKey}
        onClick={() => save({ company_id: Number(companyId), terminal_key: terminalKey, terminal_password: password }, 'Тестовый терминал сохранён')}>
        {busy ? <Icon name="Loader2" size={14} className="mr-2 animate-spin" /> : <Icon name="Save" size={14} className="mr-2" />}
        Проверить и сохранить
      </Button>
    </div>
  );
};

export default TbankCompanyTestTerminals;
