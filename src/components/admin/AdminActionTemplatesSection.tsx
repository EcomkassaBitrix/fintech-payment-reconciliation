import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import Icon from '@/components/ui/icon';
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
import { useToast } from '@/hooks/use-toast';
import { useAuth } from '@/contexts/AuthContext';
import functionUrls from '../../../backend/func2url.json';
import ActionTemplateDialog from './ActionTemplateDialog';
import ActionTemplatesTabs from './ActionTemplatesTabs';
import {
  ActionTemplateForm,
  ActionTemplateRow,
  CashProvider,
  EMPTY_TEMPLATE,
  formToPayload,
  templateToForm
} from './actionTemplatesConfig';

const API = (functionUrls as Record<string, string>)['admin-action-templates'];

const AdminActionTemplatesSection = () => {
  const { user } = useAuth();
  const { toast } = useToast();
  const [templates, setTemplates] = useState<ActionTemplateRow[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<ActionTemplateRow | null>(null);
  const [form, setForm] = useState<ActionTemplateForm>(EMPTY_TEMPLATE);
  const [toDelete, setToDelete] = useState<ActionTemplateRow | null>(null);
  const [providers, setProviders] = useState<CashProvider[]>([]);

  const load = async () => {
    if (!user) return;
    try {
      const res = await fetch(`${API}?requester_user_id=${user.user_id}`);
      const data = await res.json();
      if (data.success) {
        setTemplates(data.templates || []);
        setProviders(data.providers || []);
      }
      else toast({ title: 'Ошибка', description: data.error, variant: 'destructive' });
    } catch {
      toast({ title: 'Ошибка подключения', variant: 'destructive' });
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user]);

  const openCreate = () => {
    setEditing(null);
    setForm({ ...EMPTY_TEMPLATE, provider_id: providers[0]?.id ?? null });
    setDialogOpen(true);
  };

  const openEdit = (t: ActionTemplateRow) => {
    setEditing(t);
    setForm(templateToForm(t));
    setDialogOpen(true);
  };

  const handleSubmit = async () => {
    if (!user) return;
    setIsSaving(true);
    try {
      const res = await fetch(API, {
        method: editing ? 'PUT' : 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...formToPayload(form), id: editing?.id, requester_user_id: user.user_id })
      });
      const data = await res.json();
      if (data.success) {
        toast({ title: editing ? 'Шаблон сохранён' : 'Шаблон создан', description: form.name });
        setDialogOpen(false);
        load();
      } else {
        toast({ title: 'Ошибка', description: data.error, variant: 'destructive' });
      }
    } catch {
      toast({ title: 'Ошибка подключения', variant: 'destructive' });
    } finally {
      setIsSaving(false);
    }
  };

  // Копия шаблона: новый код (_copy, _copy2...), название «(копия)», выключена - чтобы не попала
  // клиентам до проверки. После создания сразу открывается на редактирование.
  const handleCopy = async (t: ActionTemplateRow) => {
    if (!user) return;
    const codes = new Set(templates.map((x) => x.code));
    const base = `${t.code.replace(/_copy\d*$/, '').slice(0, 42)}_copy`;
    let code = base;
    for (let i = 2; codes.has(code); i++) code = `${base}${i}`;
    const copy: ActionTemplateForm = { ...templateToForm(t), code, name: `${t.name} (копия)`.slice(0, 150), is_active: false };
    try {
      const res = await fetch(API, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...formToPayload(copy), requester_user_id: user.user_id })
      });
      const data = await res.json();
      if (!data.success) {
        toast({ title: 'Не удалось скопировать', description: data.error, variant: 'destructive' });
        return;
      }
      toast({ title: 'Копия создана', description: 'Шаблон выключен — проверьте и включите' });
      await load();
      setEditing({ ...t, id: data.id, code, name: copy.name, is_active: false, scenarios_count: 0 });
      setForm(copy);
      setDialogOpen(true);
    } catch {
      toast({ title: 'Ошибка подключения', variant: 'destructive' });
    }
  };

  const handleDelete = async () => {
    if (!user || !toDelete) return;
    const target = toDelete;
    setToDelete(null);
    try {
      const res = await fetch(API, {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: target.id, requester_user_id: user.user_id })
      });
      const data = await res.json();
      if (data.success) {
        toast({ title: 'Шаблон удалён', description: target.name });
        load();
      } else {
        toast({ title: 'Не удалось удалить', description: data.error, variant: 'destructive' });
      }
    } catch {
      toast({ title: 'Ошибка подключения', variant: 'destructive' });
    }
  };

  if (isLoading) {
    return (
      <div className="flex h-96 items-center justify-center">
        <Icon name="Loader2" className="animate-spin text-primary" size={32} />
      </div>
    );
  }

  return (
    <div className="animate-fade-in">
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h2 className="mb-2 text-3xl font-display font-bold text-foreground">Шаблоны действий</h2>
          <p className="text-muted-foreground">Что автоматизация может сделать в кассе — доступно всем компаниям платформы</p>
        </div>
        <Button onClick={openCreate} className="gap-2">
          <Icon name="Plus" size={16} />
          Создать шаблон
        </Button>
      </div>

      <ActionTemplatesTabs
        templates={templates}
        onEdit={openEdit}
        onCopy={handleCopy}
        onDelete={setToDelete}
      />

      <AlertDialog open={!!toDelete} onOpenChange={(o) => !o && setToDelete(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Удалить шаблон?</AlertDialogTitle>
            <AlertDialogDescription>
              «{toDelete?.name}» пропадёт из списка шаблонов во всех компаниях. Отменить удаление нельзя.
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

      <ActionTemplateDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        form={form}
        onChange={setForm}
        onSubmit={handleSubmit}
        isSaving={isSaving}
        isEditing={!!editing}
        scenariosCount={editing?.scenarios_count || 0}
        providers={providers}
      />
    </div>
  );
};

export default AdminActionTemplatesSection;
