import { useState } from 'react';
import { format, parseISO } from 'date-fns';
import { ru } from 'date-fns/locale';
import { Button } from '@/components/ui/button';
import { Calendar } from '@/components/ui/calendar';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import Icon from '@/components/ui/icon';

interface Props {
  value: string;
  onChange: (iso: string) => void;
}

const toIso = (d: Date) => format(d, 'yyyy-MM-dd');

const PRESETS = [
  { label: '1 день', shift: (d: Date) => d.setDate(d.getDate() + 1) },
  { label: '1 неделя', shift: (d: Date) => d.setDate(d.getDate() + 7) },
  { label: '1 месяц', shift: (d: Date) => d.setMonth(d.getMonth() + 1) },
];

const presetDate = (shift: (d: Date) => void) => {
  const d = new Date();
  shift(d);
  return toIso(d);
};

const CouponValidUntilField = ({ value, onChange }: Props) => {
  const [calendarOpen, setCalendarOpen] = useState(false);
  const activePreset = PRESETS.find((p) => presetDate(p.shift) === value)?.label;
  const selected = value ? parseISO(value) : undefined;

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-2">
        {PRESETS.map((p) => (
          <Button
            key={p.label}
            type="button"
            size="sm"
            variant={activePreset === p.label ? 'default' : 'outline'}
            onClick={() => onChange(presetDate(p.shift))}
          >
            {p.label}
          </Button>
        ))}
        <Popover open={calendarOpen} onOpenChange={setCalendarOpen}>
          <PopoverTrigger asChild>
            <Button type="button" size="sm" variant={value && !activePreset ? 'default' : 'outline'} className="gap-1.5">
              <Icon name="CalendarDays" size={14} />
              Своя дата
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-auto p-0" align="start">
            <Calendar
              mode="single"
              locale={ru}
              selected={selected}
              defaultMonth={selected}
              disabled={{ before: new Date(new Date().setHours(0, 0, 0, 0)) }}
              onSelect={(d) => {
                if (!d) return;
                onChange(toIso(d));
                setCalendarOpen(false);
              }}
              initialFocus
            />
          </PopoverContent>
        </Popover>
      </div>
      {value && (
        <div className="text-xs text-muted-foreground">
          Действует до {format(parseISO(value), 'd MMMM yyyy', { locale: ru })} включительно
        </div>
      )}
    </div>
  );
};

export default CouponValidUntilField;
