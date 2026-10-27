import { ReactNode } from 'react';
import { Navigate } from "@/lib/router-compat";
import { useAuth } from '@/contexts/AuthContext';
import Icon from '@/components/ui/icon';

const RequireAdmin = ({ children }: { children: ReactNode }) => {
  const { user, isLoading, isPlatformAdmin } = useAuth();

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <Icon name="Loader2" className="animate-spin text-primary" size={32} />
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  if (!isPlatformAdmin) {
    return <Navigate to="/app" replace />;
  }

  return <>{children}</>;
};

export default RequireAdmin;
