import { useCallback, useEffect, useState } from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle
} from '@/components/ui/alert-dialog';
import Icon from '@/components/ui/icon';
import { ToastAction } from '@/components/ui/toast';
import { useToast } from '@/hooks/use-toast';
import { useAuth } from '@/contexts/AuthContext';
import ScenarioDialog, { ScenarioForm } from '@/components/automation/ScenarioDialog';
import AutomationJournal from '@/components/automation/AutomationJournal';
import CopyScenarioDialog from '@/components/automation/CopyScenarioDialog';
import { ACTIONS, ActionTemplateOption, IntegrationOption, Scenario, TRIGGERS } from '@/components/automation/automationConfig';
import { GOALS, reachGoal } from '@/lib/metrika';
import functionUrls from '../../backend/func2url.json';

interface IntegrationRow {
  id: number;
  integration_name: string;
  provider_name: string;
  provider_slug: string;
  category_slug: string;
  status: string;
  config?: { stage?: string; protocol_version?: string };
  webhook_settings?: Record<string, boolean> | null;
}

interface AutomationPageProps {
  prefillSourceId?: number | null;
  onPrefillUsed?: () => void;
}

const AutomationPage = ({ prefillSourceId, onPrefillUsed }: AutomationPageProps = {}) => {
  const { currentCompany, companies, user, setCurrentCompanyId } = useAuth();
  const { toast } = useToast();
  const companyId = currentCompany?.id;
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [integrations, setIntegrations] = useState<IntegrationOption[]>([]);
  const [templates, setTemplates] = useState<ActionTemplateOption[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<Scenario | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [toDelete, setToDelete] = useState<Scenario | null>(null);
  const [togglingId, setTogglingId] = useState<number | null>(null);
  const [toCopy, setToCopy] = useState<Scenario | null>(null);
  const [isCopying, setIsCopying] = useState(false);
  const [journalOpen, setJournalOpen] = useState(false);
  const [journalScenarioId, setJournalScenarioId] = useState<number | null>(null);
  const openJournal = (scenarioId: number | null) => {
    setJournalScenarioId(scenarioId);
    setJournalOpen(true);
  };
  const [failedJobs, setFailedJobs] = useState(0);

  const api = functionUrls['automation-scenarios'];

  const load = useCallback(async () => {
    if (!companyId) return;
    const [sRes, iRes, tRes] = await Promise.all([
      fetch(`${api}?company_id=${companyId}`),
      fetch(`${functionUrls['integrations-list']}?company_id=${companyId}`),
      fetch(`${(functionUrls as Record<string, string>)['admin-action-templates']}?active=1`)
    ]);
    const sData = await sRes.json();
    const iData = await iRes.json();
    const tData = await tRes.json();
    setScenarios(sData.scenarios || []);
    setTemplates(tData.templates || []);
    setIntegrations(
      ((iData.user_integrations || []) as IntegrationRow[])
        .filter((i) => i.status === 'active')
        .map((i) => ({ id: i.id, name: i.integration_name, providerName: i.provider_name, providerSlug: i.provider_slug, category: i.category_slug, stage: i.config?.stage, protocolVersion: i.config?.protocol_version, webhookSettings: i.webhook_settings || undefined }))
    );
    setIsLoading(false);
  }, [api, companyId]);

  const loadFailedCount = useCallback(async () => {
    if (!companyId) return;
    const res = await fetch(`${functionUrls['automation-jobs']}?company_id=${companyId}&status=failed&limit=1`);
    const data = await res.json().catch(() => ({}));
    setFailedJobs(data.counts?.failed || 0);
  }, [companyId]);

  useEffect(() => {
    if (!journalOpen) loadFailedCount();
  }, [journalOpen, loadFailedCount]);

  useEffect(() => {
    load();
    // Открытие раздела заодно дожимает задания, застрявшие в очереди.
    if (companyId) {
      fetch(functionUrls['automation-jobs'], {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'run', company_id: companyId })
      }).catch(() => {});
    }
  }, [load, companyId]);

  const call = async (method: string, body: object) => {
    const res = await fetch(api, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ company_id: companyId, ...body })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Попробуйте ещё раз');
    return data;
  };

  const handleSave = async (form: ScenarioForm) => {
    setIsSaving(true);
    try {
      if (editing) await call('PUT', { id: editing.id, ...form });
      else {
        await call('POST', form);
        reachGoal(GOALS.scenarioAdded);
      }
      toast({ title: editing ? 'Сценарий сохранён' : 'Сценарий создан', description: editing ? undefined : 'Он остановлен — запустите переключателем' });
      setDialogOpen(false);
      await load();
    } catch (e) {
      toast({ title: 'Не удалось сохранить', description: (e as Error).message, variant: 'destructive' });
    } finally {
      setIsSaving(false);
    }
  };

  const handleToggle = async (s: Scenario) => {
    setTogglingId(s.id);
    try {
      await call('PUT', { id: s.id, status: s.status === 'active' ? 'stopped' : 'active' });
      await load();
    } catch (e) {
      toast({ title: 'Не удалось изменить', description: (e as Error).message, variant: 'destructive' });
    } finally {
      setTogglingId(null);
    }
  };

  // Копия сценария: в эту компанию - сразу открываем на редактирование; в другую - сервер
  // подбирает там такую же кассу и источник, предлагаем перейти в ту компанию.
  const handleCopy = async (targetCompanyId: number, name: string) => {
    if (!toCopy) return;
    const s = toCopy;
    setIsCopying(true);
    try {
      if (targetCompanyId === companyId) {
        const data = await call('POST', {
          name,
          trigger_type: s.trigger_type,
          source_integration_id: s.source_integration_id,
          action_type: s.action_type,
          action_template: s.action_template,
          target_integration_id: s.target_integration_id,
          field_mapping: s.field_mapping || {},
          correction_settings: s.correction_settings || {}
        });
        toast({ title: 'Сценарий скопирован', description: 'Копия остановлена — проверьте настройки и запустите' });
        setToCopy(null);
        await load();
        setEditing({ ...s, id: data.id, name, status: 'stopped', jobs_total: 0, jobs_errors: 0 });
        setDialogOpen(true);
        return;
      }
      const data = await call('POST', { action: 'copy', id: s.id, target_company_id: targetCompanyId, user_id: user?.user_id, name });
      const targetName = companies.find((c) => c.id === targetCompanyId)?.name || 'выбранную компанию';
      setToCopy(null);
      toast({
        title: `Скопировано в «${targetName}»`,
        description: data.copied_source
          ? `Вместе с интеграцией «${data.copied_source}» — у неё свой адрес хука, добавьте его в CRM. Сценарий остановлен.`
          : 'Сценарий остановлен — проверьте настройки и запустите',
        action: (
          <ToastAction altText="Перейти в компанию" onClick={() => setCurrentCompanyId(targetCompanyId)}>Перейти</ToastAction>
        )
      });
    } catch (e) {
      toast({ title: 'Не удалось скопировать', description: (e as Error).message, variant: 'destructive' });
    } finally {
      setIsCopying(false);
    }
  };

  const handleDelete = async () => {
    if (!toDelete) return;
    try {
      await call('DELETE', { id: toDelete.id });
      toast({ title: 'Сценарий удалён' });
      await load();
    } catch (e) {
      toast({ title: 'Не удалось удалить', description: (e as Error).message, variant: 'destructive' });
    } finally {
      setToDelete(null);
    }
  };

  const [prefill, setPrefill] = useState<Partial<ScenarioForm> | null>(null);

  const openCreate = () => {
    setEditing(null);
    setPrefill(null);
    setDialogOpen(true);
  };

  // Переход из «Интеграций» после подключения платёжки: новый сценарий чеков по ней.
  useEffect(() => {
    if (!prefillSourceId || isLoading) return;
    const source = integrations.find((i) => i.id === prefillSourceId);
    if (source) {
      const kassas = integrations.filter((i) => i.category === 'cash_registers');
      setEditing(null);
      setPrefill({
        name: source.providerSlug === 'moyklass' && source.stage === 'debit_new'
          ? `Зачёт аванса ${source.name}`
          : source.providerSlug === 'realtycalendar' && source.stage === 'refund'
            ? `Возвраты ${source.name}`
            : `Чек по оплатам ${source.name}`,
        trigger_type: 'new_payment',
        source_integration_id: source.id,
        action_type: 'create_receipt',
        ...(() => {
          if (source.providerSlug !== 'moyklass' && source.providerSlug !== 'realtycalendar') return {};
          const code = source.providerSlug === 'realtycalendar'
            ? (source.stage === 'refund' ? 'refund_prepayment_service' : 'prepayment_service')
            : source.stage === 'debit_new' ? 'advance_offset_service' : 'prepayment_service';
          return templates.some((t) => t.code === code) ? { action_template: code } : {};
        })(),
        target_integration_id: kassas.length === 1 ? kassas[0].id : null
      });
      setDialogOpen(true);
    }
    onPrefillUsed?.();
  }, [prefillSourceId, isLoading, integrations, templates, onPrefillUsed]);

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2 className="text-2xl sm:text-3xl font-display font-bold text-foreground mb-2">Автоматизация</h2>
          <p className="text-sm text-muted-foreground sm:text-base">Сценарии: событие в интеграции — документ в кассе</p>
        </div>
        <div className="grid grid-cols-2 gap-2 sm:flex sm:flex-wrap sm:items-center">
          <Button variant="outline" className="gap-2" onClick={() => openJournal(null)}>
            <Icon name="ScrollText" size={16} />
            Журнал
            {failedJobs > 0 && (
              <span className="rounded-full bg-destructive px-1.5 text-xs font-semibold text-destructive-foreground" title="Заданий, которые не удалось выполнить">
                {failedJobs}
              </span>
            )}
          </Button>
          <Button className="gap-2" onClick={openCreate}>
            <Icon name="Plus" size={16} />
            Новый сценарий
          </Button>
        </div>
      </div>

      {isLoading ? (
        <div className="flex h-48 items-center justify-center">
          <Icon name="Loader2" className="animate-spin text-muted-foreground" size={28} />
        </div>
      ) : scenarios.length === 0 ? (
        <Card className="border-dashed">
          <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
            <div className="flex h-14 w-14 items-center justify-center rounded-full bg-primary/15">
              <Icon name="Workflow" size={28} className="text-primary" />
            </div>
            <div className="text-lg font-semibold">Сценариев пока нет</div>
            <p className="max-w-md text-sm text-muted-foreground">
              Например: «Новый платёж в Точке → обычный чек в Екомкассе». Сервис сам подготовит данные и создаст документ.
            </p>
            <Button className="mt-2 gap-2" onClick={openCreate}>
              <Icon name="Plus" size={16} />
              Создать первый сценарий
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {scenarios.map((s) => {
            const trigger = TRIGGERS[s.trigger_type];
            const action = ACTIONS[s.action_type];
            const active = s.status === 'active';
            return (
              <Card key={s.id} className={`transition-colors ${active ? 'border-primary/40' : ''}`}>
                <CardContent className="flex flex-wrap items-start gap-3 p-3 sm:flex-nowrap sm:items-center sm:gap-4 sm:p-5">
                  <Switch
                    className="mt-0.5 sm:mt-0"
                    checked={active}
                    disabled={togglingId === s.id}
                    onCheckedChange={() => handleToggle(s)}
                    aria-label={active ? 'Остановить' : 'Запустить'}
                  />
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="min-w-0 break-words font-semibold">{s.name}</span>
                      <Badge variant="outline" className={active ? 'bg-success/15 text-success border-success/30' : 'text-muted-foreground'}>
                        {active ? 'Запущен' : 'Остановлен'}
                      </Badge>
                    </div>
                    <div className="mt-2 flex flex-col items-start gap-1.5 text-xs sm:flex-row sm:flex-wrap sm:items-center sm:gap-2 sm:text-sm">
                      <span className="inline-flex max-w-full items-center gap-1.5 break-words rounded-md bg-muted px-2 py-1">
                        <Icon name={trigger.icon} size={14} className="shrink-0 text-primary" />
                        {trigger.label}
                        {s.source_integration_name && <span className="text-muted-foreground">· {s.source_integration_name}</span>}
                      </span>
                      <Icon name="ArrowRight" size={14} className="ml-2 rotate-90 text-muted-foreground sm:ml-0 sm:rotate-0" />
                      <span className="inline-flex max-w-full items-center gap-1.5 break-words rounded-md bg-muted px-2 py-1">
                        <Icon name={action.icon} size={14} className="shrink-0 text-primary" />
                        {s.action_template_name || s.action_template}
                        {s.target_integration_name && <span className="text-muted-foreground">· {s.target_integration_name}</span>}
                      </span>
                    </div>
                    <div className="mt-2 text-xs text-muted-foreground">
                      <button
                        type="button"
                        className="underline-offset-2 hover:text-foreground hover:underline"
                        title="Открыть журнал этого сценария"
                        onClick={() => openJournal(s.id)}
                      >
                        Заданий: {s.jobs_total}
                        {s.jobs_errors > 0 && <span className="text-warning"> · с ошибкой: {s.jobs_errors}</span>}
                      </button>
                    </div>
                  </div>
                  <div className="-mb-1 -mr-1 flex w-full items-center justify-end gap-1 border-t border-border pt-1 sm:m-0 sm:w-auto sm:border-0 sm:pt-0">
                    <Button size="icon" variant="ghost" title="Копировать" onClick={() => setToCopy(s)}>
                      <Icon name="Copy" size={16} />
                    </Button>
                    <Button size="icon" variant="ghost" title="Изменить" onClick={() => { setEditing(s); setDialogOpen(true); }}>
                      <Icon name="Pencil" size={16} />
                    </Button>
                    <Button size="icon" variant="ghost" title="Удалить" className="text-destructive hover:text-destructive" onClick={() => setToDelete(s)}>
                      <Icon name="Trash2" size={16} />
                    </Button>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      <ScenarioDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        scenario={editing}
        prefill={prefill}
        integrations={integrations}
        templates={templates}
        isSaving={isSaving}
        onSave={handleSave}
      />

      <AutomationJournal
        open={journalOpen}
        onOpenChange={setJournalOpen}
        scenarioId={journalScenarioId}
        onScenarioChange={setJournalScenarioId}
        scenarios={scenarios.map((sc) => ({ id: sc.id, name: sc.name }))}
      />

      <CopyScenarioDialog
        scenario={toCopy}
        companies={companies}
        currentCompanyId={companyId ?? null}
        isCopying={isCopying}
        onOpenChange={(o) => !o && setToCopy(null)}
        onCopy={handleCopy}
      />

      <AlertDialog open={!!toDelete} onOpenChange={(o) => !o && setToDelete(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Удалить сценарий?</AlertDialogTitle>
            <AlertDialogDescription>
              «{toDelete?.name}» перестанет срабатывать. Записи в журнале сохранятся.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Отмена</AlertDialogCancel>
            <AlertDialogAction onClick={handleDelete} className="bg-destructive text-destructive-foreground hover:bg-destructive/90">
              Удалить
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
};

export default AutomationPage;