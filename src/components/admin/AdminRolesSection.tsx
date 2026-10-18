import { useState, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import Icon from '@/components/ui/icon';
import { useToast } from '@/hooks/use-toast';
import { useAuth } from '@/contexts/AuthContext';
import functionUrls from '../../../backend/func2url.json';
import AdminRoleCard, { AdminRole } from './AdminRoleCard';
import RoleEditorDialog, { RoleFormState } from './RoleEditorDialog';

const EMPTY_FORM: RoleFormState = {
  name: '',
  description: '',
  color: 'bg-info',
  modules: [],
  permissions: []
};

const AdminRolesSection = () => {
  const { user } = useAuth();
  const { toast } = useToast();
  const [roles, setRoles] = useState<AdminRole[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingRoleId, setEditingRoleId] = useState<number | null>(null);
  const [formState, setFormState] = useState<RoleFormState>(EMPTY_FORM);

  const loadRoles = async () => {
    if (!user) return;
    setIsLoading(true);
    try {
      const res = await fetch(`${functionUrls['roles-list']}?view=admin&requester_user_id=${user.user_id}`);
      const data = await res.json();
      if (data.success) {
        setRoles(data.roles || []);
      } else {
        toast({ title: 'Ошибка', description: data.error, variant: 'destructive' });
      }
    } catch {
      toast({ title: 'Ошибка подключения', variant: 'destructive' });
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadRoles();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user]);

  const openCreateDialog = () => {
    setEditingRoleId(null);
    setFormState(EMPTY_FORM);
    setDialogOpen(true);
  };

  const openEditDialog = (role: AdminRole) => {
    setEditingRoleId(role.id);
    setFormState({
      name: role.name,
      description: role.description || '',
      color: role.color,
      modules: role.modules,
      permissions: role.permissions
    });
    setDialogOpen(true);
  };

  const handleSubmit = async () => {
    if (!user) return;
    setIsSaving(true);

    try {
      const isEditing = editingRoleId !== null;
      const url = functionUrls['roles-list'];
      const res = await fetch(url, {
        method: isEditing ? 'PUT' : 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          requester_user_id: user.user_id,
          role_id: editingRoleId,
          name: formState.name,
          description: formState.description,
          color: formState.color,
          modules: formState.modules,
          permissions: formState.permissions
        })
      });
      const data = await res.json();

      if (data.success) {
        toast({ title: isEditing ? 'Роль обновлена' : 'Роль создана', description: formState.name });
        setDialogOpen(false);
        loadRoles();
      } else {
        toast({ title: 'Ошибка', description: data.error, variant: 'destructive' });
      }
    } catch {
      toast({ title: 'Ошибка подключения', variant: 'destructive' });
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async (role: AdminRole) => {
    if (!user) return;
    if (!confirm(`Удалить роль «${role.name}»?`)) return;

    try {
      const res = await fetch(functionUrls['roles-list'], {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ requester_user_id: user.user_id, role_id: role.id })
      });
      const data = await res.json();

      if (data.success) {
        toast({ title: 'Роль удалена' });
        loadRoles();
      } else {
        toast({ title: 'Ошибка', description: data.error, variant: 'destructive' });
      }
    } catch {
      toast({ title: 'Ошибка подключения', variant: 'destructive' });
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-96">
        <Icon name="Loader2" className="animate-spin text-primary" size={32} />
      </div>
    );
  }

  return (
    <div className="animate-fade-in">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h2 className="text-3xl font-display font-bold text-foreground mb-2">Роли</h2>
          <p className="text-muted-foreground">Каталог ролей, доступных во всех компаниях платформы</p>
        </div>
        <Button onClick={openCreateDialog} className="gap-2">
          <Icon name="Plus" size={16} />
          Создать роль
        </Button>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {roles.map((role) => (
          <AdminRoleCard
            key={role.id}
            role={role}
            onEdit={() => openEditDialog(role)}
            onDelete={() => handleDelete(role)}
          />
        ))}
      </div>

      <RoleEditorDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        formState={formState}
        onChange={setFormState}
        onSubmit={handleSubmit}
        isSaving={isSaving}
        isEditing={editingRoleId !== null}
      />
    </div>
  );
};

export default AdminRolesSection;
