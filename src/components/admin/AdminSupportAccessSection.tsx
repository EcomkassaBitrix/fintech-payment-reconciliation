import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import Icon from '@/components/ui/icon';
import { useAuth } from '@/contexts/AuthContext';
import { useToast } from '@/hooks/use-toast';
import { formatDateTime } from '@/lib/formatDate';
import functionUrls from '../../../backend/func2url.json';

interface SupportCompany {
  id: number;
  name: string;
  inn: string | null;
  until: string | null;
  granted_at: string | null;
  granted_by: string | null;
  last_enter_at: string | null;
}

const api = (functionUrls as Record<string, string>)['company-settings-update'];

const timeLeft = (until: string | null) => {
  if (!until) return 'Бессрочно';
  const ms = new Date(/Z|[+-]\d{2}:\d{2}$/.test(until) ? until : `${until}Z`).getTime() - Date.now();
  if (ms <= 0) return 'Истёк';
  const hours = Math.floor(ms / 3600000);
  if (hours < 24) return `Осталось ${hours} ч`;
  return `Осталось ${Math.floor(hours / 24)} дн.`;
};

const AdminSupportAccessSection = () => {
  const { refreshCompanies, setCurrentCompanyId } = useAuth();
  const { toast } = useToast();
  const navigate = useNavigate();
  const [companies, setCompanies] = useState<SupportCompany[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [enteringId, setEnteringId] = useState<number | null>(null);

  useEffect(() => {
    fetch(`${api}?admin=1`)
      .then((r) => r.json())
      .then((d) => setCompanies(d.companies || []))
      .catch(() => undefined)
      .finally(() => setIsLoading(false));
  }, []);

  const enter = async (company: SupportCompany) => {
    setEnteringId(company.id);
    try {
      const res = await fetch(api, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'enter', company_id: company.id })
      });
      const data = await res.json();
      if (!res.ok || !data.success) {
        toast({ title: 'Не удалось войти', description: data.error, variant: 'destructive' });
        return;
      }
      await refreshCompanies();
      setCurrentCompanyId(company.id);
      navigate('/app');
    } catch {
      toast({ title: 'Ошибка подключения', variant: 'destructive' });
    } finally {
      setEnteringId(null);
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-96">
        <Icon name="Loader2" className="animate-spin text-primary" size={32} />
      </div>
    );
  }

  return (
    <div className="animate-fade-in">
      <div className="mb-8">
        <h2 className="text-3xl font-display font-bold text-foreground mb-2">Доступ открыт</h2>
        <p className="text-muted-foreground">
          Клиенты, которые разрешили поддержке зайти в кабинет. Вы работаете с правами админа компании, изменения видны клиенту в журнале.
        </p>
      </div>

      {companies.length === 0 ? (
        <Card className="border-border bg-card">
          <CardContent className="p-10 text-center">
            <Icon name="LifeBuoy" size={36} className="mx-auto mb-3 text-muted-foreground" />
            <p className="text-foreground font-medium mb-1">Пока никто не открыл доступ</p>
            <p className="text-sm text-muted-foreground">
              Клиент включает доступ в своём кабинете: «Настройки» → «Доступ поддержки».
            </p>
          </CardContent>
        </Card>
      ) : (
        <Card className="border-border bg-card">
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border text-left text-muted-foreground">
                    <th className="p-4 font-medium">Компания</th>
                    <th className="p-4 font-medium">Кто открыл</th>
                    <th className="p-4 font-medium">Открыт</th>
                    <th className="p-4 font-medium">Срок</th>
                    <th className="p-4 font-medium">Ваш последний вход</th>
                    <th className="p-4" />
                  </tr>
                </thead>
                <tbody>
                  {companies.map((c) => (
                    <tr key={c.id} className="border-b border-border last:border-0">
                      <td className="p-4">
                        <p className="font-medium text-foreground">{c.name}</p>
                        {c.inn && <p className="text-xs text-muted-foreground">ИНН {c.inn}</p>}
                      </td>
                      <td className="p-4 text-foreground">{c.granted_by || '—'}</td>
                      <td className="p-4 text-muted-foreground">{formatDateTime(c.granted_at)}</td>
                      <td className="p-4">
                        <span className="text-info font-medium">{timeLeft(c.until)}</span>
                        {c.until && <p className="text-xs text-muted-foreground">до {formatDateTime(c.until)}</p>}
                      </td>
                      <td className="p-4 text-muted-foreground">{c.last_enter_at ? formatDateTime(c.last_enter_at) : 'Не входили'}</td>
                      <td className="p-4 text-right">
                        <Button size="sm" disabled={enteringId === c.id} onClick={() => enter(c)}>
                          {enteringId === c.id
                            ? <Icon name="Loader2" size={14} className="animate-spin mr-2" />
                            : <Icon name="LogIn" size={14} className="mr-2" />}
                          Войти в кабинет
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
};

export default AdminSupportAccessSection;
