import { useMemo, useState } from 'react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Input } from '@/components/ui/input';
import Icon from '@/components/ui/icon';
import ActionTemplateCard from './ActionTemplateCard';
import { ActionTemplateRow } from './actionTemplatesConfig';

interface Props {
  templates: ActionTemplateRow[];
  onEdit: (t: ActionTemplateRow) => void;
  onCopy: (t: ActionTemplateRow) => void;
  onDelete: (t: ActionTemplateRow) => void;
}

type Category = 'regular' | 'agent' | 'correction' | 'order';

const CATEGORIES: { value: Category; label: string; icon: string; byFfd: boolean }[] = [
  { value: 'regular', label: 'Обычные чеки', icon: 'Receipt', byFfd: true },
  { value: 'agent', label: 'Агентские чеки', icon: 'Handshake', byFfd: true },
  { value: 'correction', label: 'Чеки коррекции', icon: 'FilePen', byFfd: true },
  { value: 'order', label: 'Заказы', icon: 'Truck', byFfd: false }
];

const FFD_GROUPS = [
  { value: 'v4', label: 'ФФД 1.05 / 1.1', hint: 'протокол v4' },
  { value: 'v5', label: 'ФФД 1.2', hint: 'протокол v5' }
];

const categoryOf = (t: ActionTemplateRow): Category => {
  if (t.action_type === 'create_order') return 'order';
  if (t.receipt_type === 'agent') return 'agent';
  if (t.receipt_type === 'correction') return 'correction';
  return 'regular';
};

const ActionTemplatesTabs = ({ templates, onEdit, onCopy, onDelete }: Props) => {
  const [tab, setTab] = useState<Category>('regular');
  const [query, setQuery] = useState('');

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return templates;
    return templates.filter((t) => `${t.name} ${t.code} ${t.description || ''}`.toLowerCase().includes(q));
  }, [templates, query]);

  const grid = (list: ActionTemplateRow[]) => (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
      {list.map((t) => (
        <ActionTemplateCard key={t.id} t={t} onEdit={onEdit} onCopy={onCopy} onDelete={onDelete} />
      ))}
    </div>
  );

  const empty = (
    <p className="rounded-lg border border-dashed border-border p-6 text-center text-sm text-muted-foreground">
      {query ? 'Ничего не найдено' : 'Шаблонов пока нет'}
    </p>
  );

  return (
    <Tabs value={tab} onValueChange={(v) => setTab(v as Category)}>
      <div className="mb-6 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <TabsList className="h-auto flex-wrap justify-start">
          {CATEGORIES.map((c) => {
            const count = filtered.filter((t) => categoryOf(t) === c.value).length;
            return (
              <TabsTrigger key={c.value} value={c.value} className="gap-2">
                <Icon name={c.icon} size={15} fallback="Receipt" />
                {c.label}
                <span className="rounded-full bg-muted px-1.5 text-xs text-muted-foreground">{count}</span>
              </TabsTrigger>
            );
          })}
        </TabsList>
        <div className="relative w-full lg:w-72">
          <Icon name="Search" size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Поиск по названию или коду"
            className="pl-9"
          />
        </div>
      </div>

      {CATEGORIES.map((c) => {
        const list = filtered.filter((t) => categoryOf(t) === c.value);
        return (
          <TabsContent key={c.value} value={c.value} className="mt-0">
            {list.length === 0
              ? empty
              : !c.byFfd
                ? grid(list)
                : FFD_GROUPS.map((g) => {
                    const part = list.filter((t) => (t.protocol_version || 'v4') === g.value);
                    if (part.length === 0) return null;
                    return (
                      <div key={g.value} className="mb-8">
                        <div className="mb-3 flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                          <Icon name="FileText" size={16} className="text-primary" />
                          {g.label}
                          <span className="font-normal normal-case">· {g.hint} · {part.length}</span>
                        </div>
                        {grid(part)}
                      </div>
                    );
                  })}
          </TabsContent>
        );
      })}
    </Tabs>
  );
};

export default ActionTemplatesTabs;
