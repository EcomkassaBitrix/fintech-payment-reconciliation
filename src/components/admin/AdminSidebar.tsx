import { useNavigate } from "@/lib/router-compat";
import Icon from '@/components/ui/icon';
import { ADMIN_SECTIONS } from '@/config/adminSections';

interface AdminSidebarProps {
  activeSection: string;
  onSectionChange: (sectionId: string) => void;
}

const AdminSidebar = ({ activeSection, onSectionChange }: AdminSidebarProps) => {
  const navigate = useNavigate();

  return (
    <aside className="fixed left-0 top-0 h-full w-64 bg-sidebar border-r border-sidebar-border p-4">
      <div className="mb-6">
        <button onClick={() => navigate('/app')} className="flex items-center gap-2 mb-1">
          <Icon name="ShieldCheck" size={28} className="text-primary" />
          <h1 className="text-xl font-display font-bold text-primary">Админка</h1>
        </button>
        <p className="text-sm text-sidebar-foreground/60">Управление платформой</p>
      </div>

      <nav className="space-y-2">
        {ADMIN_SECTIONS.map((section) => (
          <button
            key={section.id}
            onClick={() => onSectionChange(section.id)}
            className={`w-full flex items-center gap-3 px-4 py-3 rounded-lg transition-all duration-200 ${
              activeSection === section.id
                ? 'bg-sidebar-accent text-sidebar-accent-foreground shadow-lg'
                : 'text-sidebar-foreground hover:bg-sidebar-accent/50'
            }`}
          >
            <Icon name={section.icon as any} size={20} />
            <span className="font-medium">{section.name}</span>
          </button>
        ))}
      </nav>

      <button
        onClick={() => navigate('/app')}
        className="absolute bottom-4 left-4 right-4 flex items-center gap-3 px-4 py-3 rounded-lg text-sidebar-foreground hover:bg-sidebar-accent/50 transition-colors"
      >
        <Icon name="ArrowLeft" size={20} />
        <span className="font-medium">Вернуться в ЛК</span>
      </button>
    </aside>
  );
};

export default AdminSidebar;
