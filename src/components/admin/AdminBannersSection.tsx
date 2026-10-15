import { useCallback, useEffect, useState } from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import Icon from '@/components/ui/icon';
import { useToast } from '@/hooks/use-toast';
import { useAuth } from '@/contexts/AuthContext';
import { formatDateTime } from '@/lib/formatDate';
import PageBanner from '@/components/banners/PageBanner';
import MaintenanceBlock from './MaintenanceBlock';
import { Banner, BannerPage, BannerVariant, BANNER_VARIANTS, bannersApi } from '@/components/banners/bannerTypes';

const emptyBanner = (page: string): Banner => ({ page, text: '', button_text: '', button_url: '', variant: 'info', is_active: true });

type BannerState = 'shown' | 'hidden' | 'empty';

const stateOf = (b: Banner): BannerState => (!b.text.trim() ? 'empty' : b.is_active === false ? 'hidden' : 'shown');

const STATE_BADGE: Record<BannerState, { label: string; variant: 'default' | 'secondary' | 'outline' }> = {
  shown: { label: 'Показывается', variant: 'default' },
  hidden: { label: 'Скрыт', variant: 'secondary' },
  empty: { label: 'Не задан', variant: 'outline' },
};

const AdminBannersSection = () => {
  const { user } = useAuth();
  const { toast } = useToast();
  const [pages, setPages] = useState<BannerPage[]>([]);
  const [drafts, setDrafts] = useState<Record<string, Banner>>({});
  const [saved, setSaved] = useState<Record<string, Banner>>({});
  const [openPage, setOpenPage] = useState<string | null>(null);
  const [savingPage, setSavingPage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const apply = (data: { banners: Banner[]; pages: BannerPage[] }) => {
    const byPage = Object.fromEntries((data.banners || []).map((b) => [b.page, b]));
    const full = Object.fromEntries((data.pages || []).map((p) => [p.id, byPage[p.id] ?? emptyBanner(p.id)]));
    setPages(data.pages || []);
    setSaved(full);
    setDrafts(full);
  };

  const load = useCallback(async () => {
    if (!user) return;
    const res = await fetch(`${bannersApi}?requester_user_id=${user.user_id}&section=banners`);
    const data = await res.json();
    if (res.ok) apply(data);
    else setError(data.error || 'Не удалось загрузить баннеры');
  }, [user]);

  useEffect(() => {
    load();
  }, [load]);

  const update = (page: string, patch: Partial<Banner>) =>
    setDrafts((d) => ({ ...d, [page]: { ...d[page], ...patch } }));

  const save = async (page: string, override: Partial<Banner>, message: string) => {
    if (!user) return;
    const banner = { ...drafts[page], ...override };
    setSavingPage(page);
    try {
      const res = await fetch(bannersApi, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'save_banner', requester_user_id: user.user_id, ...banner }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Не удалось сохранить');
      apply(data);
      toast({ title: message });
    } catch (e) {
      toast({ title: 'Ошибка', description: e instanceof Error ? e.message : 'Не удалось сохранить', variant: 'destructive' });
    } finally {
      setSavingPage(null);
    }
  };

  if (error) {
    return <p className="text-destructive">{error}</p>;
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-3xl font-display font-bold mb-2">Баннеры</h2>
        <p className="text-muted-foreground">
          Сообщение клиентам вверху страницы личного кабинета. Нажмите на страницу, чтобы задать текст.
          «Скрыть» убирает баннер у клиентов, но текст сохраняется - его можно снова показать одной кнопкой.
        </p>
      </div>

      <MaintenanceBlock />

      <Card>
        <CardContent className="p-0 divide-y divide-border">
          {pages.map((p) => {
            const d = drafts[p.id] ?? emptyBanner(p.id);
            const s = saved[p.id] ?? emptyBanner(p.id);
            const state = stateOf(s);
            const isOpen = openPage === p.id;
            const busy = savingPage === p.id;
            const dirty = JSON.stringify({ ...d, updated_at: null }) !== JSON.stringify({ ...s, updated_at: null });
            const buttonIncomplete = !!d.button_text.trim() !== !!d.button_url.trim();
            return (
              <div key={p.id}>
                <button
                  type="button"
                  onClick={() => setOpenPage(isOpen ? null : p.id)}
                  className="w-full flex items-center gap-3 px-5 py-4 text-left hover:bg-muted/40 transition-colors"
                >
                  <Icon name={isOpen ? 'ChevronDown' : 'ChevronRight'} size={18} className="text-muted-foreground shrink-0" />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-medium">{p.name}</span>
                      <Badge variant={STATE_BADGE[state].variant}>{STATE_BADGE[state].label}</Badge>
                    </div>
                    <p className="text-sm text-muted-foreground truncate">
                      {s.text.trim() || (p.id === 'all' ? 'Показывается на всех страницах кабинета' : 'Баннера нет')}
                    </p>
                  </div>
                  {s.updated_at && state !== 'empty' && (
                    <span className="text-xs text-muted-foreground shrink-0 hidden md:block">
                      {formatDateTime(s.updated_at)}
                    </span>
                  )}
                </button>

                {isOpen && (
                  <div className="px-5 pb-5 pt-1 space-y-4 bg-muted/20">
                    <div>
                      <label className="text-sm text-muted-foreground">Текст</label>
                      <Textarea
                        value={d.text}
                        onChange={(e) => update(p.id, { text: e.target.value })}
                        placeholder="Что увидят клиенты"
                        rows={2}
                        maxLength={2000}
                      />
                    </div>
                    <div className="grid gap-4 md:grid-cols-3">
                      <div>
                        <label className="text-sm text-muted-foreground">Текст кнопки</label>
                        <Input value={d.button_text} onChange={(e) => update(p.id, { button_text: e.target.value })} placeholder="Например: Подробнее" maxLength={80} />
                      </div>
                      <div>
                        <label className="text-sm text-muted-foreground">Ссылка кнопки</label>
                        <Input value={d.button_url} onChange={(e) => update(p.id, { button_url: e.target.value })} placeholder="https://..." maxLength={500} />
                      </div>
                      <div>
                        <label className="text-sm text-muted-foreground">Вид</label>
                        <Select value={d.variant} onValueChange={(v) => update(p.id, { variant: v as BannerVariant })}>
                          <SelectTrigger><SelectValue /></SelectTrigger>
                          <SelectContent>
                            {(Object.keys(BANNER_VARIANTS) as BannerVariant[]).map((v) => (
                              <SelectItem key={v} value={v}>{BANNER_VARIANTS[v].label}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                    </div>
                    {buttonIncomplete && (
                      <p className="text-xs text-muted-foreground">Кнопка появится, только когда заполнены и текст, и ссылка.</p>
                    )}

                    {d.text.trim() && (
                      <div>
                        <p className="text-xs text-muted-foreground mb-2">Так увидит клиент:</p>
                        <PageBanner banner={d} />
                      </div>
                    )}

                    <div className="flex flex-wrap gap-2">
                      <Button
                        onClick={() => save(p.id, { is_active: true }, 'Баннер сохранён и показывается')}
                        disabled={busy || !d.text.trim() || (!dirty && state === 'shown')}
                      >
                        {busy ? <Icon name="Loader2" size={16} className="mr-2 animate-spin" /> : <Icon name="Eye" size={16} className="mr-2" />}
                        {state === 'hidden' && !dirty ? 'Показать снова' : 'Сохранить и показать'}
                      </Button>
                      {state === 'shown' && (
                        <Button variant="outline" onClick={() => save(p.id, { ...s, is_active: false }, 'Баннер скрыт, текст сохранён')} disabled={busy}>
                          <Icon name="EyeOff" size={16} className="mr-2" />
                          Скрыть
                        </Button>
                      )}
                      {state !== 'empty' && (
                        <Button
                          variant="ghost"
                          className="text-destructive hover:text-destructive"
                          onClick={() => save(p.id, { ...emptyBanner(p.id) }, 'Баннер удалён')}
                          disabled={busy}
                        >
                          <Icon name="Trash2" size={16} className="mr-2" />
                          Удалить
                        </Button>
                      )}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </CardContent>
      </Card>
    </div>
  );
};

export default AdminBannersSection;
