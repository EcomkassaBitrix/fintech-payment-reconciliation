import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Progress } from '@/components/ui/progress';
import Icon from '@/components/ui/icon';
import { useAuth } from '@/contexts/AuthContext';
import NotificationPreferences from '@/components/settings/NotificationPreferences';
import { finishOnboarding, ONBOARDING_EVENT, ONBOARDING_STEPS, onboardingStep, saveOnboardingStep } from '@/lib/onboarding';
import OnboardingSections from './OnboardingSections';
import OnboardingProfile from './OnboardingProfile';
import OnboardingIntegrations from './OnboardingIntegrations';
import OnboardingReceipts from './OnboardingReceipts';
import { useCompanyIntegrations } from './useCompanyIntegrations';

const TITLES = [
  { title: 'Что где находится', text: 'Коротко о разделах кабинета' },
  { title: 'Ваш профиль', text: 'Как к вам обращаться и куда писать' },
  { title: 'Куда присылать уведомления', text: 'Все уведомления видны в колокольчике. Выберите, куда их дублировать лично вам' },
  { title: 'Подключите сервисы', text: 'Базовый набор: банк, платёжный сервис и касса' },
  { title: 'Автоматические чеки', text: 'Пробивать чеки по оплатам без вашего участия' }
];

interface Props {
  onConnect?: (categorySlug: string) => void;
  onSetupReceipts?: (integrationId: number) => void;
}

const OnboardingWizard = ({ onConnect, onSetupReceipts }: Props) => {
  const { currentCompany } = useAuth();
  const companyId = currentCompany?.id;
  const [step, setStep] = useState<number | null>(() => onboardingStep(companyId));
  const [open, setOpen] = useState(true);
  const integrations = useCompanyIntegrations(step !== null && step >= 3 ? companyId : undefined);

  useEffect(() => {
    setStep(onboardingStep(companyId));
    setOpen(true);
    const restart = () => {
      setStep(onboardingStep(companyId));
      setOpen(true);
    };
    window.addEventListener(ONBOARDING_EVENT, restart);
    return () => window.removeEventListener(ONBOARDING_EVENT, restart);
  }, [companyId]);

  if (!companyId || step === null) return null;

  const goTo = (next: number) => {
    if (next >= ONBOARDING_STEPS) {
      finishOnboarding(companyId);
      setStep(null);
      return;
    }
    saveOnboardingStep(companyId, next);
    setStep(next);
  };

  const finish = () => {
    finishOnboarding(companyId);
    setStep(null);
  };

  const leaveFor = (run: () => void) => {
    setOpen(false);
    run();
  };

  const resume = () => {
    setOpen(true);
    integrations.reload();
  };

  if (!open) {
    return (
      <div className="fixed bottom-4 right-4 z-40 flex items-center gap-2 rounded-full border border-border bg-card p-1.5 pl-4 shadow-lg">
        <span className="text-sm">Настройка: шаг {step + 1} из {ONBOARDING_STEPS}</span>
        <Button size="sm" className="rounded-full" onClick={resume}>
          Продолжить
        </Button>
      </div>
    );
  }

  const { title, text } = TITLES[step];
  const isLast = step === ONBOARDING_STEPS - 1;

  return (
    <Dialog open onOpenChange={(v) => !v && setOpen(false)}>
      <DialogContent className="max-h-[90vh] max-w-2xl overflow-y-auto">
        <DialogHeader>
          <div className="mb-1 flex items-center justify-between text-xs text-muted-foreground">
            <span>Шаг {step + 1} из {ONBOARDING_STEPS}</span>
            <button type="button" className="underline-offset-2 hover:underline" onClick={finish}>
              Пропустить настройку
            </button>
          </div>
          <Progress value={((step + 1) / ONBOARDING_STEPS) * 100} className="h-1.5" />
          <DialogTitle className="pt-3">{title}</DialogTitle>
          <DialogDescription>{text}</DialogDescription>
        </DialogHeader>

        <div className="py-2">
          {step === 0 && <OnboardingSections />}
          {step === 1 && <OnboardingProfile onSaved={() => goTo(2)} />}
          {step === 2 && (
            <NotificationPreferences embedded />
          )}
          {step === 3 && (
            <OnboardingIntegrations
              items={integrations.items}
              isLoading={integrations.isLoading}
              onConnect={onConnect ? (slug) => leaveFor(() => onConnect(slug)) : undefined}
            />
          )}
          {step === 4 && (
            <OnboardingReceipts
              items={integrations.items}
              isLoading={integrations.isLoading}
              onSetupReceipts={onSetupReceipts ? (id) => leaveFor(() => onSetupReceipts(id)) : undefined}
            />
          )}
        </div>

        <div className="flex flex-wrap justify-between gap-2 border-t border-border pt-4">
          <Button variant="ghost" className="gap-1.5" disabled={step === 0} onClick={() => goTo(step - 1)}>
            <Icon name="ArrowLeft" size={16} />
            Назад
          </Button>
          <Button className="gap-1.5" variant={step === 1 ? 'outline' : 'default'} onClick={() => goTo(step + 1)}>
            {isLast ? 'Завершить' : step === 1 ? 'Пропустить' : 'Далее'}
            <Icon name={isLast ? 'Check' : 'ArrowRight'} size={16} />
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
};

export default OnboardingWizard;
