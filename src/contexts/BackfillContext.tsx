import { createContext, useContext, useState, useCallback, useRef, ReactNode } from 'react';
import functionUrls from '../../backend/func2url.json';

export type BackfillPhase = 'idle' | 'running' | 'done';

export interface BankIntegration {
  id: number;
  name: string;
}

interface EcomkassaProgress {
  processed: number;
  total: number;
  inserted: number;
}

interface BankResult {
  inserted: number;
  total: number;
}

interface StartConfig {
  companyId: number;
  dateFrom: Date;
  dateTo: Date;
  hasEcomkassa: boolean;
  orderTypes: string[];
  statuses: string[];
  typeStatuses?: Record<string, string[]>;
  hasOfd: boolean;
  bankIntegrations: BankIntegration[];
  acquiringIntegrations?: (BankIntegration & { statuses: string[] })[];
  ecomkassaNames?: string[];
  ofdNames?: string[];
}

interface BackfillContextValue {
  isDialogOpen: boolean;
  openDialog: () => void;
  closeDialog: () => void;
  reset: () => void;
  phase: BackfillPhase;
  companyId: number | null;
  dateFrom: Date | null;
  dateTo: Date | null;
  ecomkassaProgress: EcomkassaProgress;
  ofdResult: { inserted: number; total: number } | null;
  bankResults: Record<number, BankResult>;
  errors: string[];
  completedTick: number;
  lastConfig: StartConfig | null;
  start: (config: StartConfig) => void;
}

const BackfillContext = createContext<BackfillContextValue | undefined>(undefined);

const emptyProgress: EcomkassaProgress = { processed: 0, total: 0, inserted: 0 };

const toLocalDate = (d: Date) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;

export const BackfillProvider = ({ children }: { children: ReactNode }) => {
  const [isDialogOpen, setIsDialogOpen] = useState(false);
  const [phase, setPhase] = useState<BackfillPhase>('idle');
  const [companyId, setCompanyId] = useState<number | null>(null);
  const [dateFrom, setDateFrom] = useState<Date | null>(null);
  const [dateTo, setDateTo] = useState<Date | null>(null);
  const [ecomkassaProgress, setEcomkassaProgress] = useState<EcomkassaProgress>(emptyProgress);
  const [ofdResult, setOfdResult] = useState<{ inserted: number; total: number } | null>(null);
  const [bankResults, setBankResults] = useState<Record<number, BankResult>>({});
  const [errors, setErrors] = useState<string[]>([]);
  const [completedTick, setCompletedTick] = useState(0);
  const [lastConfig, setLastConfig] = useState<StartConfig | null>(null);

  // Провайдер смонтирован один раз на весь сеанс приложения (в App.tsx, вне
  // Index/страниц) - переключение вкладок внутри /app или закрытие диалога
  // НЕ размонтирует этот компонент, поэтому запущенные ниже async-функции
  // продолжают выполняться и обновлять состояние независимо от того, какая
  // страница отрисована на экране в данный момент.
  const runningRef = useRef(false);

  const runEcomkassaBackfill = useCallback(async (
    companyIdArg: number, from: Date, to: Date, orderTypes: string[], statuses: string[],
    typeStatuses?: Record<string, string[]>
  ) => {
    let offset = 0;
    let done = false;
    let totalInserted = 0;
    let matchedTotal = 0;
    // Счётчик подряд идущих неудач на ОДНОМ и том же offset - если запрос
    // не задеплоился/упал по таймауту (напр. 504 от платформы на большой
    // пачке), пробуем этот же offset ещё раз вместо того, чтобы бросать всю
    // дозагрузку - иначе счета (INVC), чей report() медленнее чеков, могли
    // не догрузиться при единичном сетевом сбое.
    let attemptsAtOffset = 0;
    const MAX_ATTEMPTS_PER_OFFSET = 3;

    try {
      while (!done) {
        let res: Response;
        try {
          res = await fetch(functionUrls['ecomkassa-fetch-orders'], {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              company_id: companyIdArg,
              date_from: from.toISOString(),
              date_to: to.toISOString(),
              order_types: orderTypes,
              statuses,
              type_statuses: typeStatuses,
              offset,
              batch_size: 8
            })
          });
        } catch {
          attemptsAtOffset += 1;
          if (attemptsAtOffset >= MAX_ATTEMPTS_PER_OFFSET) {
            setErrors((prev) => [...prev, 'Екомкасса: сбой сети, попробуйте ещё раз']);
            return;
          }
          continue;
        }

        // Не-JSON/5xx ответ (напр. 504 таймаут от платформы) - тоже повторяем
        // на том же offset, а не считаем это окончательным провалом.
        let data: { success?: boolean; error?: string; matched_total: number; inserted: number; next_offset?: number; processed: number; done: boolean } | null;
        try {
          data = await res.json();
        } catch {
          data = null;
        }

        if (!res.ok || !data || !data.success) {
          attemptsAtOffset += 1;
          if (attemptsAtOffset >= MAX_ATTEMPTS_PER_OFFSET) {
            setErrors((prev) => [...prev, data?.error || 'Не удалось загрузить данные из Екомкассы']);
            return;
          }
          continue;
        }

        attemptsAtOffset = 0;
        matchedTotal = data.matched_total;
        totalInserted += data.inserted;
        offset = data.next_offset ?? offset + data.processed;
        done = data.done;

        setEcomkassaProgress({ processed: offset, total: matchedTotal, inserted: totalInserted });
      }
    } catch {
      setErrors((prev) => [...prev, 'Екомкасса: сбой сети, попробуйте ещё раз']);
    }
  }, []);

  const runOfdBackfill = useCallback(async (companyIdArg: number, from: Date, to: Date) => {
    try {
      const res = await fetch(functionUrls['ofd-fetch-receipts'], {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          company_id: companyIdArg,
          date_from: from.toISOString(),
          date_to: to.toISOString()
        })
      });
      const data = await res.json();

      if (!res.ok || !data.success) {
        setErrors((prev) => [...prev, data.error || 'Не удалось загрузить чеки ОФД']);
        return;
      }

      setOfdResult({ inserted: data.inserted ?? 0, total: data.total_receipts ?? 0 });
    } catch {
      setErrors((prev) => [...prev, 'ОФД: сбой сети, попробуйте ещё раз']);
    }
  }, []);

  const runBankBackfill = useCallback(async (integration: BankIntegration, from: Date, to: Date) => {
    // Банк (особенно Точка) формирует выписку асинхронно и иногда не успевает
    // за отведённое функции время - это временный сбой, повторный запрос
    // обычно проходит сразу. Повторяем до 3 раз, прежде чем показать ошибку.
    const MAX_ATTEMPTS = 3;
    try {
      let data: { success?: boolean; error?: string; inserted?: number; total_transactions?: number } | null = null;
      let ok = false;
      for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
        try {
          const res = await fetch(functionUrls['bank-statement-sync'], {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            // Выписка банка - по календарным дням, поэтому шлём локальные даты
            // (YYYY-MM-DD), а не toISOString(): в UTC полночь по Москве - это
            // 21:00 предыдущего дня, и период "29.09" уезжал на "28.09".
            body: JSON.stringify({
              integration_id: integration.id,
              date_from: toLocalDate(from),
              date_to: toLocalDate(to)
            })
          });
          data = await res.json().catch(() => null);
          ok = res.ok && !!data?.success;
        } catch {
          ok = false;
        }
        if (ok) break;
        if (attempt < MAX_ATTEMPTS) await new Promise((r) => setTimeout(r, 1500));
      }

      if (!ok) {
        setErrors((prev) => [...prev, `${integration.name}: ${data?.error || 'не удалось загрузить выписку'}`]);
        return;
      }

      setBankResults((prev) => ({
        ...prev,
        [integration.id]: { inserted: data.inserted ?? 0, total: data.total_transactions ?? data.inserted ?? 0 }
      }));
    } catch {
      setErrors((prev) => [...prev, `${integration.name}: сбой сети, попробуйте ещё раз`]);
    }
  }, []);

  // Интернет-эквайринг (Альфа-Банк, ЮKassa, Точка, CloudPayments): платежи за период
  // постранично по курсору сервера, результат - в той же строке, что и банки.
  const runAcquiringBackfill = useCallback(async (
    companyIdArg: number, integration: BankIntegration & { statuses: string[] }, from: Date, to: Date
  ) => {
    let cursor: Record<string, unknown> | null = null;
    let inserted = 0;
    let found = 0;
    let attempts = 0;
    try {
      for (;;) {
        let data: { success?: boolean; error?: string; found?: number; inserted?: number; next_cursor?: Record<string, unknown> | null; done?: boolean } | null = null;
        try {
          const res = await fetch(functionUrls['acquiring-fetch-payments'], {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              company_id: companyIdArg,
              integration_id: integration.id,
              date_from: from.toISOString(),
              date_to: to.toISOString(),
              statuses: integration.statuses,
              cursor
            })
          });
          data = await res.json().catch(() => null);
          if (!res.ok && !data?.error) data = null;
        } catch {
          data = null;
        }
        if (!data || (!data.success && !data.error)) {
          attempts += 1;
          if (attempts >= 3) {
            setErrors((prev) => [...prev, `${integration.name}: сбой сети, попробуйте ещё раз`]);
            return;
          }
          continue;
        }
        if (!data.success) {
          setErrors((prev) => [...prev, `${integration.name}: ${data?.error}`]);
          return;
        }
        attempts = 0;
        inserted += data.inserted ?? 0;
        found += data.found ?? 0;
        setBankResults((prev) => ({ ...prev, [integration.id]: { inserted, total: found } }));
        if (data.done || !data.next_cursor) return;
        cursor = data.next_cursor;
      }
    } catch {
      setErrors((prev) => [...prev, `${integration.name}: сбой сети, попробуйте ещё раз`]);
    }
  }, []);

  const start = useCallback((config: StartConfig) => {
    // Запрет параллельного запуска - если процесс уже идёт (даже если диалог
    // сейчас свёрнут/страница не открыта), новый запуск игнорируется.
    if (runningRef.current) return;
    runningRef.current = true;

    setLastConfig(config);
    setCompanyId(config.companyId);
    setDateFrom(config.dateFrom);
    setDateTo(config.dateTo);
    setEcomkassaProgress(emptyProgress);
    setOfdResult(null);
    setBankResults({});
    setErrors([]);
    setPhase('running');
    setIsDialogOpen(true);

    const tasks: Promise<void>[] = [];
    if (config.hasEcomkassa) {
      tasks.push(runEcomkassaBackfill(config.companyId, config.dateFrom, config.dateTo, config.orderTypes, config.statuses, config.typeStatuses));
    }
    if (config.hasOfd) {
      tasks.push(runOfdBackfill(config.companyId, config.dateFrom, config.dateTo));
    }
    config.bankIntegrations.forEach((bi) => {
      tasks.push(runBankBackfill(bi, config.dateFrom, config.dateTo));
    });
    (config.acquiringIntegrations || []).forEach((ai) => {
      tasks.push(runAcquiringBackfill(config.companyId, ai, config.dateFrom, config.dateTo));
    });

    // .finally здесь гарантированно сработает независимо от того, смонтирован
    // ли сейчас диалог/страница - состояние живёт в этом провайдере, а не в них.
    Promise.all(tasks).finally(() => {
      runningRef.current = false;
      setPhase('done');
      setCompletedTick((t) => t + 1);
    });
  }, [runEcomkassaBackfill, runOfdBackfill, runBankBackfill, runAcquiringBackfill]);

  const openDialog = useCallback(() => setIsDialogOpen(true), []);
  const closeDialog = useCallback(() => setIsDialogOpen(false), []);

  const reset = useCallback(() => {
    if (runningRef.current) return;
    setPhase('idle');
    setEcomkassaProgress(emptyProgress);
    setOfdResult(null);
    setBankResults({});
    setErrors([]);
    setCompanyId(null);
    setDateFrom(null);
    setDateTo(null);
    setLastConfig(null);
  }, []);

  return (
    <BackfillContext.Provider
      value={{
        isDialogOpen, openDialog, closeDialog, reset,
        phase, companyId, dateFrom, dateTo,
        ecomkassaProgress, ofdResult, bankResults, errors,
        completedTick, lastConfig, start
      }}
    >
      {children}
    </BackfillContext.Provider>
  );
};

export const useBackfill = () => {
  const ctx = useContext(BackfillContext);
  if (!ctx) throw new Error('useBackfill must be used within BackfillProvider');
  return ctx;
};