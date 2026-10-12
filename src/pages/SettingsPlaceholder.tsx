import { useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import Icon from '@/components/ui/icon';
import { useToast } from '@/hooks/use-toast';
import { useAuth } from '@/contexts/AuthContext';
import { TIMEZONE_OPTIONS, DEFAULT_TIMEZONE } from '@/lib/formatDate';
import functionUrls from '../../backend/func2url.json';
import { canOpenModule, effectiveModules } from '@/config/modules';
import SupportAccessCard from '@/components/settings/SupportAccessCard';

const SettingsPlaceholder = () => {
  const { currentCompany, refreshCompanies } = useAuth();
  const { toast } = useToast();
  const [timezone, setTimezone] = useState(currentCompany?.timezone || DEFAULT_TIMEZONE);
  const [isSaving, setIsSaving] = useState(false);

  // Часовой пояс - настройка компании, доступна ролям с разделом «Настройки».
  // Личные уведомления - на отдельной странице «Уведомления» (меню профиля).
  const canEditCompany = canOpenModule(effectiveModules(currentCompany), 'settings');
  const hasChanges = timezone !== (currentCompany?.timezone || DEFAULT_TIMEZONE);

  const handleSave = async () => {
    if (!currentCompany) return;
    setIsSaving(true);
    try {
      const response = await fetch(functionUrls['company-settings-update'], {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ company_id: currentCompany.id, timezone })
      });
      const data = await response.json();

      if (response.ok && data.success) {
        toast({ title: 'Настройки сохранены' });
        await refreshCompanies();
      } else {
        toast({
          title: 'Ошибка',
          description: data.error || 'Не удалось сохранить настройки',
          variant: 'destructive'
        });
      }
    } catch {
      toast({ title: 'Ошибка подключения', variant: 'destructive' });
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="animate-fade-in space-y-6">
      <div>
        <h2 className="text-2xl sm:text-3xl font-display font-bold text-foreground mb-2">Настройки</h2>
        <p className="text-muted-foreground">Конфигурация системы и параметры</p>
      </div>

      {canEditCompany && (
        <Card className="border-border bg-card">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Icon name="Clock" size={20} />
              Часовой пояс
            </CardTitle>
            <CardDescription>
              Влияет на отображение даты и времени во всех разделах — событиях, чеках, логах вебхуков
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="max-w-sm">
              <Select value={timezone} onValueChange={setTimezone}>
                <SelectTrigger>
                  <SelectValue placeholder="Выберите часовой пояс" />
                </SelectTrigger>
                <SelectContent>
                  {TIMEZONE_OPTIONS.map((tz) => (
                    <SelectItem key={tz.value} value={tz.value}>
                      {tz.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <Button onClick={handleSave} disabled={!hasChanges || isSaving}>
              {isSaving ? (
                <Icon name="Loader2" className="animate-spin mr-2" size={16} />
              ) : (
                <Icon name="Check" size={16} className="mr-2" />
              )}
              Сохранить
            </Button>
          </CardContent>
        </Card>
      )}
      {currentCompany && !currentCompany.support_access
        && ['owner', 'admin'].includes(currentCompany.role_slug) && (
        <SupportAccessCard companyId={currentCompany.id} timezone={currentCompany.timezone} />
      )}
      {!canEditCompany && (
        <p className="text-sm text-muted-foreground">
          Настройки компании доступны владельцу. Личные уведомления — в меню профиля, пункт «Уведомления».
        </p>
      )}
    </div>
  );
};

export default SettingsPlaceholder;