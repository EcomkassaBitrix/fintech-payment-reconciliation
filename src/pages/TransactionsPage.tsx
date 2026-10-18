import { useState, useEffect, useMemo } from 'react';
import Icon from '@/components/ui/icon';
import { useToast } from '@/hooks/use-toast';
import { useAuth } from '@/contexts/AuthContext';
import { useBackfill } from '@/contexts/BackfillContext';
import { DateFilter } from '@/components/transactions/TransactionsFilters';
import TransactionDetailsDialog from '@/components/transactions/TransactionDetailsDialog';
import DeleteTransactionsDialog from '@/components/transactions/DeleteTransactionsDialog';
import TransactionsPageHeader from '@/components/transactions/TransactionsPageHeader';
import TransactionsSummaryCards from '@/components/transactions/TransactionsSummaryCards';
import TransactionsRegistryCard from '@/components/transactions/TransactionsRegistryCard';
import { Transaction, TransactionType } from '@/components/transactions/transactionsTypes';
import { groupTransactions, nodeKey } from '@/lib/transactionGrouping';
import { useTransactionsFeed } from '@/hooks/useTransactionsFeed';
import { exportTransactionsToExcel } from '@/lib/exportTransactions';
import { DEFAULT_TIMEZONE } from '@/lib/formatDate';
import { TypeFilter } from '@/lib/transactionTypeFilter';
import functionUrls from '../../backend/func2url.json';
import { resyncGateway } from '@/lib/gatewayResync';

interface TransactionsPageProps {
  initialDateFilter?: DateFilter | null;
  initialTypeFilter?: TypeFilter | null;
  initialUnmatchedOnly?: boolean;
}

const TransactionsPage = ({ initialDateFilter = null, initialTypeFilter = null, initialUnmatchedOnly = false }: TransactionsPageProps) => {
  const [selectedTx, setSelectedTx] = useState<Transaction | null>(null);
  const [showDetails, setShowDetails] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [showUnmatchedOnly, setShowUnmatchedOnly] = useState(initialUnmatchedOnly);
  const [dateFilter, setDateFilter] = useState<DateFilter | null>(initialDateFilter);
  const [typeFilter, setTypeFilter] = useState<TransactionType[]>(initialTypeFilter?.types ?? []);
  const [selectedTxByKey, setSelectedTxByKey] = useState<Map<string, Transaction>>(new Map());
  const [isLinking, setIsLinking] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [detachingKey, setDetachingKey] = useState<string | null>(null);
  const { toast } = useToast();
  const { currentCompany, cronEnabled } = useAuth();
  const companyId = currentCompany?.id;
  const { completedTick } = useBackfill();

  const feed = useTransactionsFeed(
    companyId,
    { dateFilter, searchQuery, showUnmatchedOnly, types: typeFilter },
    (message) => toast({ title: 'Ошибка загрузки', description: message, variant: 'destructive' })
  );
  const { transactions, contextTransactions, totalsByType, isLoading, isRefreshing } = feed;
  const fetchTransactions = () => feed.reload(true);

  const [isExporting, setIsExporting] = useState(false);
  const handleExport = async () => {
    setIsExporting(true);
    try {
      const all = await feed.fetchAllFiltered();
      if (!all) return;
      if (all.length === 0) {
        toast({ title: 'Нечего выгружать', description: 'Под выбранные фильтры не попало ни одной записи' });
        return;
      }
      await exportTransactionsToExcel({
        transactions: all,
        timezone: currentCompany?.timezone || DEFAULT_TIMEZONE,
        companyName: currentCompany?.name,
        dateFilter
      });
      toast({ title: 'Файл готов', description: `Выгружено записей: ${all.length}` });
    } catch (e) {
      console.error('Выгрузка транзакций:', e);
      const message = e instanceof Error ? e.message : String(e);
      // После обновления сайта браузер может держать старую версию страницы - модуль выгрузки не загружается.
      const staleBuild = /dynamically imported module|Importing a module script failed|Loading chunk/i.test(message);
      toast({
        title: 'Не удалось выгрузить',
        description: staleBuild ? 'Сайт обновился - обновите страницу (F5) и повторите' : `Попробуйте ещё раз. Причина: ${message}`,
        variant: 'destructive'
      });
    } finally {
      setIsExporting(false);
    }
  };

  useEffect(() => {
    if (!companyId) return;

    resyncGateway(companyId, cronEnabled).then((changed) => {
      if (changed) {
        fetchTransactions();
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [companyId]);

  // Дозагрузка запускается со страницы «События»; когда она завершается,
  // реестр транзакций тоже подхватывает новые данные.
  const isFirstCompletedTick = completedTick === 0;
  useEffect(() => {
    if (isFirstCompletedTick) return;
    fetchTransactions();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [completedTick]);

  const handleRowClick = (tx: Transaction) => {
    setSelectedTx(tx);
    setShowDetails(true);
  };

  const handleToggleSelect = (tx: Transaction) => {
    setSelectedTxByKey((prev) => {
      const next = new Map(prev);
      const key = nodeKey(tx);
      if (next.has(key)) next.delete(key);
      else next.set(key, tx);
      return next;
    });
  };

  const clearSelection = () => setSelectedTxByKey(new Map());

  const handleLink = async () => {
    if (!companyId || selectedTxByKey.size < 2) return;
    setIsLinking(true);
    try {
      const items = Array.from(selectedTxByKey.values()).map((tx) => ({
        type: tx.type,
        source: tx.source,
        id: tx.id
      }));
      const response = await fetch(functionUrls['transactions-link'], {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ company_id: companyId, items })
      });
      const data = await response.json();

      if (response.ok && data.success) {
        toast({ title: 'Связано', description: `Транзакции (${items.length}) объединены в одну группу` });
        clearSelection();
        fetchTransactions();
      } else {
        toast({
          title: 'Не удалось связать',
          description: data.error || 'Попробуйте ещё раз',
          variant: 'destructive'
        });
      }
    } catch {
      toast({ title: 'Ошибка подключения', description: 'Проверьте интернет-соединение', variant: 'destructive' });
    } finally {
      setIsLinking(false);
    }
  };

  // Вывод ОДНОЙ записи из группы (кнопка-магнит) - остальные участники
  // группы остаются связанными между собой.
  const handleDetach = async (tx: Transaction) => {
    if (!companyId) return;
    const key = nodeKey(tx);
    setDetachingKey(key);
    try {
      const response = await fetch(functionUrls['transactions-link'], {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ company_id: companyId, mode: 'detach', item: { type: tx.type, source: tx.source, id: tx.id } })
      });
      const data = await response.json();
      if (response.ok && data.success) {
        toast({ title: 'Связь разорвана', description: `«${tx.title}» выведена из группы` });
        await fetchTransactions();
      } else {
        toast({ title: 'Не удалось разорвать связь', description: data.error || 'Попробуйте ещё раз', variant: 'destructive' });
      }
    } catch {
      toast({ title: 'Ошибка подключения', description: 'Проверьте интернет-соединение', variant: 'destructive' });
    } finally {
      setDetachingKey(null);
    }
  };

  const handleDeleteConfirmed = async () => {
    if (!companyId || selectedTxByKey.size === 0) return;
    setIsDeleting(true);
    try {
      const items = Array.from(selectedTxByKey.values()).map((tx) => ({ type: tx.type, id: tx.id }));
      const response = await fetch(functionUrls['transactions-remove'], {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ company_id: companyId, items })
      });
      const data = await response.json();

      if (response.ok && data.success) {
        const skippedCount = data.skipped?.length || 0;
        toast({
          title: 'Удалено',
          description: skippedCount > 0
            ? `Удалено ${data.removed_count} из ${items.length} — часть записей уже не найдена`
            : `Удалено транзакций: ${data.removed_count}`
        });
        clearSelection();
        setShowDeleteConfirm(false);
        fetchTransactions();
      } else {
        toast({
          title: 'Не удалось удалить',
          description: data.error || 'Попробуйте ещё раз',
          variant: 'destructive'
        });
      }
    } catch {
      toast({ title: 'Ошибка подключения', description: 'Проверьте интернет-соединение', variant: 'destructive' });
    } finally {
      setIsDeleting(false);
    }
  };

  // Строки страницы уже отфильтрованы сервером. Участники тех же групп, не
  // попавшие под фильтр (contextTransactions), нужны только для расчёта
  // связей и окна деталей - в реестр они не выводятся.
  const allKnown = useMemo(() => [...transactions, ...contextTransactions], [transactions, contextTransactions]);
  const visibleKeys = useMemo(() => new Set(transactions.map(nodeKey)), [transactions]);

  const groups = useMemo(
    () =>
      groupTransactions(allKnown)
        .map((g) => ({ ...g, items: g.items.filter((i) => visibleKeys.has(nodeKey(i))) }))
        .filter((g) => g.items.length > 0),
    [allKnown, visibleKeys]
  );

  const isFiltered = Boolean(dateFilter) || showUnmatchedOnly || searchQuery.trim() !== '' || typeFilter.length > 0;

  const matchedCountByType = useMemo(() => {
    const counts: Partial<Record<string, number>> = {};
    Object.entries(totalsByType).forEach(([type, t]) => {
      counts[type] = t?.matched_count ?? 0;
    });
    return counts;
  }, [totalsByType]);

  const relatedItems = useMemo(() => {
    if (!selectedTx) return [];
    const key = nodeKey(selectedTx);
    return (
      groupTransactions(allKnown)
        .find((g) => g.items.some((i) => nodeKey(i) === key))
        ?.items.filter((i) => nodeKey(i) !== key) || []
    );
  }, [allKnown, selectedTx]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-96">
        <div className="text-center">
          <Icon name="Loader2" className="animate-spin mx-auto mb-2" size={32} />
          <p className="text-muted-foreground">Загрузка транзакций...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in">
      <TransactionsPageHeader
        isRefreshing={isRefreshing}
        onRefresh={fetchTransactions}
        onExport={handleExport}
        isExporting={isExporting}
      />

      <TransactionsSummaryCards totalsByType={totalsByType} matchedCountByType={matchedCountByType} isFiltered={isFiltered} />

      <TransactionsRegistryCard
        groups={groups}
        searchQuery={searchQuery}
        setSearchQuery={setSearchQuery}
        dateFilter={dateFilter}
        setDateFilter={setDateFilter}
        typeFilter={typeFilter}
        setTypeFilter={setTypeFilter}
        showUnmatchedOnly={showUnmatchedOnly}
        setShowUnmatchedOnly={setShowUnmatchedOnly}
        selectedTxByKey={selectedTxByKey}
        isLinking={isLinking}
        onLink={handleLink}
        onDeleteClick={() => setShowDeleteConfirm(true)}
        onClearSelection={clearSelection}
        onRowClick={handleRowClick}
        onToggleSelect={handleToggleSelect}
        onDetach={handleDetach}
        detachingKey={detachingKey}
        hasMore={feed.hasMore}
        isLoadingMore={feed.isLoadingMore}
        onLoadMore={feed.loadMore}
        totalCount={feed.totalCount}
        loadedCount={transactions.length}
      />

      <TransactionDetailsDialog
        transaction={selectedTx}
        relatedItems={relatedItems}
        onDetach={handleDetach}
        detachingKey={detachingKey}
        open={showDetails}
        onOpenChange={setShowDetails}
      />

      <DeleteTransactionsDialog
        open={showDeleteConfirm}
        count={selectedTxByKey.size}
        onOpenChange={setShowDeleteConfirm}
        onConfirm={handleDeleteConfirmed}
        isDeleting={isDeleting}
      />
    </div>
  );
};

export default TransactionsPage;