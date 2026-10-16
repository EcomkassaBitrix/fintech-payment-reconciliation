import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import Icon from '@/components/ui/icon';
import { useAuth } from '@/contexts/AuthContext';
import MoyklassMappingBlock from './MoyklassMappingBlock';
import ScenarioAgentBlock, { agentProblems } from './ScenarioAgentBlock';
import ScenarioStep from './ScenarioStep';
import ScenarioSourceSelect from './ScenarioSourceSelect';
import ScenarioTemplateFields from './ScenarioTemplateFields';
import ScenarioCorrectionFields from './ScenarioCorrectionFields';
import ScenarioTargetSelect from './ScenarioTargetSelect';
import ScenarioPaymentStatuses from './ScenarioPaymentStatuses';
import { notifyOptionsFor } from '@/components/integrations/providerFieldsConfig';
import ScenarioCrmMapping from './ScenarioCrmMapping';
import ScenarioDiscrepancyFields from './ScenarioDiscrepancyFields';
import {
  ACTIONS,
  AGENT_MAPPING_FIELDS,
  ActionTemplate,
  ActionTemplateOption,
  ActionType,
  CorrectionSettings,
  DEFAULT_DISCREPANCY_DELAY,
  IntegrationOption,
  MAPPING_FIELDS,
  Scenario,
  TARGET_CATEGORIES,
  TRIGGERS,
  TriggerType,
  moyklassDefaultMapping,
  realtycalendarDefaultMapping
} from './automationConfig';

export interface ScenarioForm {
  name: string;
  trigger_type: TriggerType;
  source_integration_id: number | null;
  action_type: ActionType;
  action_template: ActionTemplate;
  target_integration_id: number | null;
  field_mapping: Record<string, unknown>;
  correction_settings: CorrectionSettings;
}

interface ScenarioDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  scenario: Scenario | null;
  prefill?: Partial<ScenarioForm> | null;
  integrations: IntegrationOption[];
  templates: ActionTemplateOption[];
  isSaving: boolean;
  onSave: (form: ScenarioForm) => void;
}

const emptyForm: ScenarioForm = {
  name: '',
  trigger_type: 'new_payment',
  source_integration_id: null,
  action_type: 'create_receipt',
  action_template: 'regular',
  target_integration_id: null,
  field_mapping: {},
  correction_settings: {}
};

const ScenarioDialog = ({ open, onOpenChange, scenario, prefill, integrations, templates: allTemplates, isSaving, onSave }: ScenarioDialogProps) => {
  const [form, setForm] = useState<ScenarioForm>(emptyForm);
  const { currentCompany } = useAuth();

  useEffect(() => {
    if (!open) return;
    setForm(
      scenario
        ? {
            name: scenario.name,
            trigger_type: scenario.trigger_type,
            source_integration_id: scenario.source_integration_id,
            action_type: scenario.action_type,
            action_template: scenario.action_template,
            target_integration_id: scenario.target_integration_id,
            field_mapping: scenario.field_mapping || {},
            correction_settings: scenario.correction_settings || {}
          }
        : {
            ...emptyForm,
            action_template: allTemplates.find((t) => t.action_type === emptyForm.action_type)?.code || '',
            ...(prefill || {})
          }
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, scenario]);

  const trigger = TRIGGERS[form.trigger_type];
  const sourceOptions = trigger.sourceCategories
    ? integrations.filter((i) => trigger.sourceCategories?.includes(i.category) || (!!i.providerSlug && trigger.sourceCategories?.includes(i.providerSlug)))
    : [];
  const targetOptions = integrations.filter((i) => TARGET_CATEGORIES.includes(i.category));
  // Чеки - только под версию ФФД кассы: выбранной в сценарии, иначе всех подключённых касс.
  // У касс без указанной версии - по умолчанию v4 (ФФД 1.1), как при отправке чека.
  const targetKassa = targetOptions.find((i) => i.id === form.target_integration_id);
  const kassaVersions = new Set((targetKassa ? [targetKassa] : targetOptions).map((i) => i.protocolVersion || 'v4'));
  const templates = allTemplates.filter(
    (t) =>
      t.action_type === form.action_type &&
      (form.action_type !== 'create_receipt' || !kassaVersions.size || kassaVersions.has(t.protocol_version || 'v4'))
  );
  // Выключенный в админке шаблон остаётся видимым у сценария, который уже на нём настроен.
  if (scenario && form.action_template && !templates.some((t) => t.code === form.action_template) && scenario.action_type === form.action_type) {
    templates.push({ code: form.action_template, name: scenario.action_template_name || form.action_template, action_type: form.action_type, description: null });
  }
  const ffdLabel = form.action_type === 'create_receipt' && kassaVersions.size === 1
    ? (kassaVersions.has('v5') ? 'ФФД 1.2' : 'ФФД 1.1')
    : null;
  const currentTemplate = templates.find((t) => t.code === form.action_template);
  const templateMismatch = open && !scenario && !!form.action_template && !currentTemplate && templates.length > 0;
  useEffect(() => {
    if (templateMismatch) setForm((f) => ({ ...f, action_template: templates[0].code }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [templateMismatch]);
  const isCorrection = form.action_type === 'create_receipt' && currentTemplate?.receipt_type === 'correction';
  const isV5 = currentTemplate?.protocol_version === 'v5';
  const cs = form.correction_settings || {};
  const setCs = (patch: CorrectionSettings) => setForm({ ...form, correction_settings: { ...cs, ...patch } });
  const askEmail = form.action_type === 'create_receipt' && !!currentTemplate && !currentTemplate.default_email;
  const emailInvalid = askEmail && !!cs.default_email?.trim() && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(cs.default_email.trim());
  const askNumber = isCorrection && !currentTemplate?.correction_base_number;
  const askName = isCorrection && !isV5 && !currentTemplate?.correction_base_name;
  const askCashier = form.action_type === 'create_order' && !!currentTemplate?.auto_deliver && !currentTemplate?.cashier_name;
  const dateLabel =
    currentTemplate?.correction_date_source === 'today'
      ? 'текущая дата'
      : currentTemplate?.correction_date_source === 'fixed'
        ? 'задана в шаблоне'
        : 'дата платежа';
  const correctionMissing = isCorrection
    ? [
        askNumber && !isV5 && !cs.correction_base_number?.trim() && 'номер основания',
        askName && !cs.correction_base_name?.trim() && 'описание коррекции'
      ].filter(Boolean)
    : [];
  const sourceIntegration = integrations.find((i) => i.id === form.source_integration_id);
  const isAmo = sourceIntegration?.providerSlug === 'amocrm';
  const isBitrix = sourceIntegration?.providerSlug === 'bitrix24' || isAmo;
  const isRk = sourceIntegration?.providerSlug === 'realtycalendar';
  const isMoyklass = sourceIntegration?.providerSlug === 'moyklass' || isRk;
  // НДС для чека без корзины - у платёжек; в CRM, «Мой Класс» и RealtyCalendar НДС задаётся в «Состав чека».
  const askVat = form.action_type === 'create_receipt' && !!currentTemplate && !currentTemplate.vat &&
    !(isCorrection && !isV5) && !trigger.needsMapping && !isMoyklass;
  const moyklassOffset = isRk ? sourceIntegration?.stage === 'refund' : isMoyklass && sourceIntegration?.stage === 'debit_new';
  const sourceDefaults = (slug?: string, stage?: string) =>
    slug === 'realtycalendar' ? realtycalendarDefaultMapping() : moyklassDefaultMapping(stage === 'debit_new');
  const isAgent = form.action_type === 'create_receipt' && currentTemplate?.receipt_type === 'agent';
  // Поля поставщика, сопоставленные с CRM, в блоке «Агентский чек» не обязательны.
  const agentFromCrm = isAgent && trigger.needsMapping && isBitrix
    ? AGENT_MAPPING_FIELDS.filter((f) => String(form.field_mapping[f.key] || '').trim()).map((f) => f.agentKey)
    : [];
  const agentMissing = isAgent ? agentProblems(currentTemplate, cs.agent, agentFromCrm) : [];
  let step = 1;

  // Сценарий «Мой Класс» без сопоставления (создан раньше или из предложения после подключения) - поля по умолчанию.
  useEffect(() => {
    if (open && isMoyklass && !form.field_mapping.order_id) {
      setForm((f) => ({ ...f, field_mapping: { ...sourceDefaults(sourceIntegration?.providerSlug, sourceIntegration?.stage), ...f.field_mapping } }));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, isMoyklass, moyklassOffset, form.field_mapping.order_id]);

  const missingMapping = trigger.needsMapping || isMoyklass
    ? MAPPING_FIELDS.filter((f) => f.required && !String(form.field_mapping[f.key] || '').trim())
    : [];
  const fixedItems = (form.field_mapping.fixed_items as { name: string; price: string }[] | undefined) || [];
  const itemsInvalid =
    (trigger.needsMapping || isMoyklass) &&
    form.field_mapping.items_mode === 'fixed' &&
    !fixedItems.some((i) => i.name?.trim() && (isMoyklass ? /\{[\w.]+\}|\d/.test(String(i.price)) : Number(String(i.price).replace(',', '.')) > 0));
  const canSave =
    !!form.name.trim() &&
    (!trigger.sourceCategories || !!form.source_integration_id) &&
    !!form.target_integration_id &&
    !!currentTemplate &&
    missingMapping.length === 0 &&
    correctionMissing.length === 0 &&
    agentMissing.length === 0 &&
    !emailInvalid &&
    !itemsInvalid &&
    !isSaving;

  const setTrigger = (value: TriggerType) => {
    const allowed = TRIGGERS[value].actions;
    const actionType = allowed && !allowed.includes(form.action_type) ? allowed[0] : form.action_type;
    setForm({
      ...form,
      trigger_type: value,
      source_integration_id: null,
      action_type: actionType,
      action_template:
        actionType === form.action_type
          ? form.action_template
          : allTemplates.find((t) => t.action_type === actionType)?.code || '',
      field_mapping:
        value === 'discrepancy'
          ? { delay_minutes: Number(form.field_mapping.delay_minutes) || DEFAULT_DISCREPANCY_DELAY, discrepancy_kind: 'missing_receipt', verify_mode: 'none' }
          : form.trigger_type === 'discrepancy'
            ? {}
            : form.field_mapping
    });
  };
  const actionKeys = (trigger.actions || (Object.keys(ACTIONS) as ActionType[]));
  const setAction = (value: ActionType) =>
    setForm({ ...form, action_type: value, action_template: allTemplates.find((t) => t.action_type === value)?.code || '' });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="h-[100dvh] max-h-[100dvh] w-screen max-w-none content-start overflow-y-auto overflow-x-hidden rounded-none border-0 p-4 sm:h-auto sm:max-h-[90vh] sm:w-[calc(100vw-1.5rem)] sm:max-w-3xl sm:rounded-lg sm:border sm:p-6 [&>*]:min-w-0">
        <DialogHeader className="pr-8 text-left">
          <DialogTitle>{scenario ? 'Сценарий' : 'Новый сценарий'}</DialogTitle>
          <DialogDescription>Что должно произойти — и какой документ создать в кассе</DialogDescription>
        </DialogHeader>

        <div className="space-y-5 py-2">
          <div className="space-y-2">
            <Label>Название</Label>
            <Input
              placeholder="Чек на каждую оплату СБП"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
          </div>

          <ScenarioStep n={step++} title="Источник">
            <div className="grid grid-cols-3 gap-2">
              {(Object.keys(TRIGGERS) as TriggerType[]).map((key) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => setTrigger(key)}
                  className={`flex flex-col items-center gap-1.5 rounded-lg border-2 p-2 text-center transition-all sm:gap-2 sm:p-3 ${
                    form.trigger_type === key ? 'border-primary bg-primary/5' : 'border-border hover:border-primary/50'
                  }`}
                >
                  <Icon name={TRIGGERS[key].icon} size={20} className={form.trigger_type === key ? 'text-primary' : 'text-muted-foreground'} />
                  <span className="text-xs font-medium">{TRIGGERS[key].label}</span>
                </button>
              ))}
            </div>
            <p className="text-xs text-muted-foreground">{trigger.description}</p>
          </ScenarioStep>

          {trigger.sourceCategories && (
            <ScenarioStep n={step++} title="Интеграция-источник">
              <ScenarioSourceSelect
                form={form}
                setForm={setForm}
                integrations={integrations}
                sourceOptions={sourceOptions}
                sourceIntegration={sourceIntegration}
                trigger={trigger}
                sourceDefaults={sourceDefaults}
              />
            </ScenarioStep>
          )}

          {form.trigger_type === 'new_payment' && sourceIntegration?.category === 'payments' && notifyOptionsFor(sourceIntegration.providerSlug).length > 0 && (
            <ScenarioStep n={step++} title="Когда запускать">
              <ScenarioPaymentStatuses
                source={sourceIntegration}
                value={Array.isArray(form.field_mapping.payment_statuses) ? (form.field_mapping.payment_statuses as string[]) : []}
                onChange={(statuses) => setForm({ ...form, field_mapping: { ...form.field_mapping, payment_statuses: statuses } })}
              />
            </ScenarioStep>
          )}

          {form.trigger_type === 'discrepancy' && (
            <ScenarioDiscrepancyFields
              mapping={form.field_mapping}
              onChange={(patch) => setForm({ ...form, field_mapping: { ...form.field_mapping, ...patch } })}
              startStep={(step += 3) - 3}
              hasPayments={integrations.some((i) => i.category === 'payments')}
              hasBanks={integrations.some((i) => i.category === 'banks')}
            />
          )}

          <ScenarioStep n={step++} title="Действие">
            <div className={`grid gap-2 ${actionKeys.length > 1 ? 'grid-cols-1 sm:grid-cols-2' : 'grid-cols-1'}`}>
              {actionKeys.map((key) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => setAction(key)}
                  className={`flex items-center gap-2 rounded-lg border-2 px-3 py-2.5 text-sm font-medium transition-all ${
                    form.action_type === key ? 'border-primary bg-primary/5' : 'border-border hover:border-primary/50'
                  }`}
                >
                  <Icon name={ACTIONS[key].icon} size={18} className={form.action_type === key ? 'text-primary' : 'text-muted-foreground'} />
                  {ACTIONS[key].label}
                </button>
              ))}
            </div>
          </ScenarioStep>

          <ScenarioStep n={step++} title="Шаблон действия">
            <ScenarioTemplateFields
              actionTemplate={form.action_template}
              onTemplateChange={(v) => setForm({ ...form, action_template: v })}
              templates={templates}
              currentTemplate={currentTemplate}
              cs={cs}
              setCs={setCs}
              askEmail={askEmail}
              emailInvalid={emailInvalid}
              askVat={askVat}
              askCashier={askCashier}
              isCorrection={isCorrection}
            />
            {ffdLabel && (
              <p className="text-xs text-muted-foreground">Показаны шаблоны под {ffdLabel} — по настройке {targetKassa ? 'выбранной кассы' : 'подключённой кассы'}</p>
            )}
          </ScenarioStep>

          {isAgent && currentTemplate && (
            <ScenarioStep n={step++} title="Агентский чек">
              <ScenarioAgentBlock
                template={currentTemplate}
                values={cs.agent || {}}
                onChange={(agent) => setCs({ agent })}
                fromCrm={agentFromCrm}
              />
              {agentMissing.length > 0 && (
                <p className="text-xs text-destructive">Заполните или исправьте: {agentMissing.join(', ')}</p>
              )}
            </ScenarioStep>
          )}

          {isCorrection && (
            <ScenarioStep n={step++} title="Чек коррекции">
              <ScenarioCorrectionFields
                cs={cs}
                setCs={setCs}
                isV5={isV5}
                dateLabel={dateLabel}
                askNumber={askNumber}
                askName={askName}
                correctionMissing={correctionMissing}
              />
            </ScenarioStep>
          )}

          <ScenarioStep n={step++} title="Касса">
            <ScenarioTargetSelect
              value={form.target_integration_id}
              onChange={(id) => setForm({ ...form, target_integration_id: id })}
              targetOptions={targetOptions}
            />
          </ScenarioStep>

          {isMoyklass && form.source_integration_id && currentCompany && (
            <ScenarioStep n={step++} title={`Сопоставление полей ${isRk ? 'RealtyCalendar' : '«Мой Класс»'}`}>
              <MoyklassMappingBlock
                companyId={currentCompany.id}
                integrationId={form.source_integration_id}
                offset={moyklassOffset}
                provider={isRk ? 'realtycalendar' : 'moyklass'}
                mapping={form.field_mapping}
                onChange={(m) => setForm({ ...form, field_mapping: m })}
                templatePaymentMethod={currentTemplate?.payment_method}
                templateVat={currentTemplate?.vat}
              />
            </ScenarioStep>
          )}

          {trigger.needsMapping && (
            <ScenarioStep n={step++} title="Сопоставление полей">
              <ScenarioCrmMapping
                sourceIntegrationId={form.source_integration_id}
                companyId={currentCompany?.id}
                isBitrix={isBitrix}
                isAmo={isAmo}
                isAgent={isAgent}
                mapping={form.field_mapping}
                onChange={(m) => setForm({ ...form, field_mapping: m })}
                currentTemplate={currentTemplate}
                cs={cs}
              />
            </ScenarioStep>
          )}
        </div>

        <div className="sticky -bottom-4 -mx-4 space-y-2 border-t border-border bg-background/95 px-4 pb-4 pt-3 backdrop-blur sm:static sm:mx-0 sm:border-0 sm:bg-transparent sm:p-0">
        <Button className="w-full gap-2" disabled={!canSave} onClick={() => onSave(form)}>
          <Icon name={isSaving ? 'Loader2' : 'Check'} size={16} className={isSaving ? 'animate-spin' : ''} />
          {scenario ? 'Сохранить' : 'Создать сценарий'}
        </Button>
        {!scenario && <p className="text-center text-xs text-muted-foreground">Сценарий создаётся остановленным — запустите его, когда будете готовы</p>}
        </div>
      </DialogContent>
    </Dialog>
  );
};

export default ScenarioDialog;
