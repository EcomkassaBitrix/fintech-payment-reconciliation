import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import Icon from '@/components/ui/icon';

export interface FilterOption<T extends string> {
  value: T;
  label: string;
  icon: string;
}

interface MultiSelectFilterButtonProps<T extends string> {
  title: string;
  options: FilterOption<T>[];
  value: T[];
  onChange: (value: T[]) => void;
  extraToggle?: ExtraToggle | ExtraToggle[];
}

interface ExtraToggle {
  label: string;
  icon: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  iconClassName?: string;
}

// Пустой выбор = показываются все записи (состояние по умолчанию, без цифры на кнопке).
function MultiSelectFilterButton<T extends string>({ title, options, value, onChange, extraToggle }: MultiSelectFilterButtonProps<T>) {
  const [open, setOpen] = useState(false);
  const toggles = extraToggle ? (Array.isArray(extraToggle) ? extraToggle : [extraToggle]) : [];
  const count = value.length + toggles.filter((t) => t.checked).length;

  const resetAll = () => {
    onChange([]);
    toggles.forEach((t) => t.onChange(false));
  };

  const toggle = (item: T) => {
    onChange(value.includes(item) ? value.filter((v) => v !== item) : [...value, item]);
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant={count > 0 ? 'default' : 'outline'}
          size="icon"
          className="relative h-9 w-9 shrink-0"
          aria-label={title}
          title={title}
        >
          <Icon name="SlidersHorizontal" size={16} />
          {count > 0 && (
            <span className="absolute -top-2 -right-2 flex h-5 min-w-5 items-center justify-center rounded-full bg-destructive px-1 text-[11px] font-bold leading-none text-destructive-foreground">
              {count}
            </span>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-64 p-0">
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <span className="text-sm font-semibold">{title}</span>
          {count > 0 && (
            <button type="button" className="text-xs font-medium text-primary hover:underline" onClick={resetAll}>
              Сбросить
            </button>
          )}
        </div>
        <div className="space-y-1 p-2">
          {options.map((option) => (
            <label
              key={option.value}
              className="flex cursor-pointer items-center gap-3 rounded-md px-2 py-2 text-sm hover:bg-muted"
            >
              <Checkbox checked={value.includes(option.value)} onCheckedChange={() => toggle(option.value)} />
              <Icon name={option.icon} size={14} className="text-muted-foreground" />
              <span>{option.label}</span>
            </label>
          ))}
        </div>
        {toggles.length > 0 && (
          <div className="border-t border-border p-2 space-y-1">
            {toggles.map((t) => (
              <label key={t.label} className="flex cursor-pointer items-center gap-3 rounded-md px-2 py-2 text-sm hover:bg-muted">
                <Checkbox checked={t.checked} onCheckedChange={(c) => t.onChange(c === true)} />
                <Icon name={t.icon} size={14} className={t.iconClassName ?? 'text-destructive'} />
                <span>{t.label}</span>
              </label>
            ))}
          </div>
        )}
        <p className="border-t border-border px-4 py-2 text-xs text-muted-foreground">
          Ничего не отмечено — показываются все записи
        </p>
      </PopoverContent>
    </Popover>
  );
}

export default MultiSelectFilterButton;
