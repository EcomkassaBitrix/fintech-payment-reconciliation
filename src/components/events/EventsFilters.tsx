import { Input } from '@/components/ui/input';
import DateRangeFilter, { DateFilter } from '@/components/filters/DateRangeFilter';
import MultiSelectFilterButton from '@/components/filters/MultiSelectFilterButton';
import { EVENT_SOURCE_OPTIONS, EventSource } from '@/components/events/eventsTypes';

interface EventsFiltersProps {
  searchQuery: string;
  setSearchQuery: (query: string) => void;
  dateFilter: DateFilter | null;
  setDateFilter: (value: DateFilter | null) => void;
  sourceFilter: EventSource[];
  setSourceFilter: (value: EventSource[]) => void;
  errorsOnly: boolean;
  setErrorsOnly: (value: boolean) => void;
  pendingOnly: boolean;
  setPendingOnly: (value: boolean) => void;
}

const EventsFilters = ({
  searchQuery,
  setSearchQuery,
  dateFilter,
  setDateFilter,
  sourceFilter,
  setSourceFilter,
  errorsOnly,
  setErrorsOnly,
  pendingOnly,
  setPendingOnly
}: EventsFiltersProps) => {
  return (
    <div className="flex items-center gap-3 pl-0.5 pr-0.5 pt-2 pb-0.5 sm:pr-2">
      <div className="flex flex-wrap items-center gap-3 flex-1 min-w-0">
        <Input
          placeholder="Номер события, сумма или данные вебхука"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="w-full sm:w-auto sm:flex-1 sm:min-w-[180px] sm:max-w-md"
        />
        <MultiSelectFilterButton
          title="Источники"
          options={EVENT_SOURCE_OPTIONS}
          value={sourceFilter}
          onChange={setSourceFilter}
          extraToggle={[
            { label: 'Только ошибки', icon: 'CircleAlert', checked: errorsOnly, onChange: setErrorsOnly },
            {
              label: 'Только ожидают оплату', icon: 'Hourglass', checked: pendingOnly, onChange: setPendingOnly,
              iconClassName: 'text-muted-foreground'
            }
          ]}
        />
        <DateRangeFilter
          value={dateFilter}
          onChange={setDateFilter}
          onReset={() => {
            setDateFilter(null);
            setSourceFilter([]);
            setErrorsOnly(false);
            setPendingOnly(false);
          }}
        />
      </div>
    </div>
  );
};

export default EventsFilters;
