import { Checkbox } from '@/components/ui/checkbox';
import { Label } from '@/components/ui/label';
import Icon from '@/components/ui/icon';
import { ActiveSources, DOC_CATEGORIES, Selection, SourceItem, categoryItems } from './backfillSources';

interface BackfillDocTypesProps {
  selection: Selection;
  sources: ActiveSources;
  disabled: boolean;
  onChange: (key: string, statusIds: string[]) => void;
}

const IntegrationRow = ({ item, chosen, disabled, onChange }: {
  item: SourceItem;
  chosen: string[];
  disabled: boolean;
  onChange: (key: string, statusIds: string[]) => void;
}) => {
  const all = item.statuses.length > 0 && item.statuses.every((st) => chosen.includes(st.id));
  const some = chosen.length > 0;
  const id = `bf-${item.key}`;

  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-2">
        <Checkbox
          id={id}
          checked={all ? true : some ? 'indeterminate' : false}
          onCheckedChange={() => onChange(item.key, all ? [] : item.statuses.map((st) => st.id))}
          disabled={disabled}
        />
        <Label htmlFor={id} className="text-sm font-normal cursor-pointer">{item.name}</Label>
      </div>
      <div className="pl-6 space-y-1.5">
        {item.statuses.map((st) => {
          const stId = `${id}-${st.id}`;
          const checked = chosen.includes(st.id);
          return (
            <div key={st.id} className="flex items-center gap-2">
              <Checkbox
                id={stId}
                checked={checked}
                onCheckedChange={() =>
                  onChange(item.key, checked ? chosen.filter((c) => c !== st.id) : [...chosen, st.id])
                }
                disabled={disabled}
              />
              <Label htmlFor={stId} className="text-xs font-normal text-muted-foreground cursor-pointer">
                {st.label}
              </Label>
            </div>
          );
        })}
      </div>
    </div>
  );
};

const BackfillDocTypes = ({ selection, sources, disabled, onChange }: BackfillDocTypesProps) => {
  const categories = DOC_CATEGORIES
    .map((c) => ({ category: c, items: categoryItems(c, sources) }))
    .filter((c) =>
      c.items.length > 0 ||
      (sources.disabled?.[c.category.id] || []).length > 0 ||
      (c.category.id === 'payments' && sources.webhookOnly.length > 0)
    );

  return (
    <div className="space-y-3">
      <Label className="text-sm font-medium">Документы</Label>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {categories.map(({ category, items }) => (
          <div key={category.id} className="space-y-2">
            <div className="flex items-center gap-1.5 text-sm font-medium">
              <Icon name={category.icon} size={14} />
              {category.label}
            </div>
            <div className="space-y-2">
              {items.map((item) => (
                <IntegrationRow
                  key={item.key}
                  item={item}
                  chosen={selection[item.key] || []}
                  disabled={disabled}
                  onChange={onChange}
                />
              ))}
              {(sources.disabled?.[category.id] || []).map((d) => (
                <div key={`off-${d.id}`} className="flex items-start gap-2 text-muted-foreground">
                  <div className="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-sm border border-muted-foreground/40 bg-muted">
                    <Icon name="X" size={12} />
                  </div>
                  <div className="text-sm">
                    {d.name}
                    <div className="text-xs">Интеграция выключена</div>
                  </div>
                </div>
              ))}
              {category.id === 'payments' && sources.webhookOnly.map((w) => (
                <div key={w.id} className="flex items-start gap-2 text-muted-foreground">
                  <Icon name="Info" size={14} className="mt-0.5 shrink-0" />
                  <div className="text-sm">
                    {w.name}
                    <div className="text-xs">Загрузка за период недоступна — платежи приходят вебхуками</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default BackfillDocTypes;
