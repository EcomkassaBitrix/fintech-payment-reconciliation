import Icon from '@/components/ui/icon';

const OptionList = <T extends string>({
  options,
  value,
  onSelect,
  disabled
}: {
  options: { value: T; label: string; description: string; icon?: string }[];
  value: T;
  onSelect: (v: T) => void;
  disabled?: (v: T) => string | false;
}) => (
  <div className="divide-y divide-border overflow-hidden rounded-lg border border-border">
    {options.map((o) => {
      const off = disabled?.(o.value);
      const active = value === o.value;
      return (
        <button
          key={o.value}
          type="button"
          disabled={!!off}
          onClick={() => onSelect(o.value)}
          className={`flex w-full items-start gap-3 px-3 py-2.5 text-left transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
            active ? 'bg-primary/5' : 'hover:bg-muted/50'
          }`}
        >
          <span
            className={`mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full border-2 ${active ? 'border-primary' : 'border-muted-foreground/50'}`}
          >
            {active && <span className="h-2 w-2 rounded-full bg-primary" />}
          </span>
          {o.icon && <Icon name={o.icon} size={18} className={`mt-px shrink-0 ${active ? 'text-primary' : 'text-muted-foreground'}`} />}
          <span className="min-w-0">
            <span className="block text-sm font-medium">{o.label}</span>
            <span className="mt-0.5 block text-xs text-muted-foreground">{off || o.description}</span>
          </span>
        </button>
      );
    })}
  </div>
);

export default OptionList;
