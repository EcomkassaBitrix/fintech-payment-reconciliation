import { useState } from 'react';
import AdminSidebar from '@/components/admin/AdminSidebar';
import AdminPlaceholder from '@/components/admin/AdminPlaceholder';
import AdminCompaniesSection from '@/components/admin/AdminCompaniesSection';
import AdminRolesSection from '@/components/admin/AdminRolesSection';
import AdminSupportAccessSection from '@/components/admin/AdminSupportAccessSection';
import AdminActionTemplatesSection from '@/components/admin/AdminActionTemplatesSection';
import AdminSettingsSection from '@/components/admin/AdminSettingsSection';
import AdminTariffsSection from '@/components/admin/AdminTariffsSection';
import AdminCasesSection from '@/components/admin/AdminCasesSection';
import AdminBannersSection from '@/components/admin/AdminBannersSection';

const Admin = () => {
  const [activeSection, setActiveSection] = useState('companies');

  return (
    <div className="min-h-screen bg-background">
      <AdminSidebar activeSection={activeSection} onSectionChange={setActiveSection} />

      <main className="ml-64 p-8">
        {activeSection === 'companies' && <AdminCompaniesSection />}
        {activeSection === 'support' && <AdminSupportAccessSection />}
        {activeSection === 'roles' && <AdminRolesSection />}
        {activeSection === 'action_templates' && <AdminActionTemplatesSection />}
        {activeSection === 'settings' && <AdminSettingsSection />}
        {activeSection === 'tariffs' && <AdminTariffsSection />}
        {activeSection === 'banners' && <AdminBannersSection />}
        {activeSection === 'cases' && <AdminCasesSection />}
        {activeSection === 'integrations' && (
          <AdminPlaceholder icon="Plug" title="Интеграции CRM" description="Каталог провайдеров, доступных всем компаниям" />
        )}
      </main>
    </div>
  );
};

export default Admin;