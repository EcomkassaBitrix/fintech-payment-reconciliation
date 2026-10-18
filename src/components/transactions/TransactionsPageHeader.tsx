import { Button } from '@/components/ui/button';
import Icon from '@/components/ui/icon';

interface TransactionsPageHeaderProps {
  isRefreshing: boolean;
  onRefresh: () => void;
  onExport: () => void;
  isExporting: boolean;
}

const TransactionsPageHeader = ({ isRefreshing, onRefresh, onExport, isExporting }: TransactionsPageHeaderProps) => {
  return (
    <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
      <div>
        <h2 className="text-2xl sm:text-3xl font-display font-bold text-foreground mb-2">Транзакции</h2>
        <p className="text-sm text-muted-foreground sm:text-base">
          Готовые данные для сверки: платежи, чеки и деньги на счету
        </p>
      </div>
      <div className="grid grid-cols-[1fr_auto] gap-2 sm:flex sm:flex-wrap sm:items-center">
        <Button onClick={onExport} variant="outline" className="gap-2" disabled={isExporting} title="Выгрузить записи по текущим фильтрам">
          <Icon name={isExporting ? 'Loader2' : 'FileSpreadsheet'} size={16} className={isExporting ? 'animate-spin' : ''} />
          {isExporting ? 'Готовлю файл…' : 'Excel'}
        </Button>
        <Button onClick={onRefresh} variant="outline" size="icon" title="Обновить" disabled={isRefreshing}>
          <Icon name="RefreshCw" size={16} className={isRefreshing ? 'animate-spin' : ''} />
        </Button>
      </div>
    </div>
  );
};

export default TransactionsPageHeader;