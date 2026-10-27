import { useEffect, useState } from 'react';
import { useNavigate, useParams } from "@/lib/router-compat";
import Icon from '@/components/ui/icon';
import { useAuth } from '@/contexts/AuthContext';
import { rememberPromo } from '@/lib/pendingPromo';
import functionUrls from '../../backend/func2url.json';

const api = (functionUrls as Record<string, string>)['subscription-checkout'];

const PromoLinkPage = () => {
  const { code } = useParams();
  const { user, companies, isLoading } = useAuth();
  const navigate = useNavigate();
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    if (!code) {
      setChecked(true);
      return;
    }
    let cancelled = false;
    (async () => {
      let error: string | null = null;
      try {
        const res = await fetch(`${api}?coupon_status=${encodeURIComponent(code)}`);
        const d = await res.json();
        if (res.ok && !d.valid) error = d.error || 'Промокод недействителен';
      } catch {
        error = null;
      }
      if (cancelled) return;
      rememberPromo(code, error);
      setChecked(true);
    })();
    return () => {
      cancelled = true;
    };
  }, [code]);

  useEffect(() => {
    if (isLoading || !checked) return;
    if (!user) navigate('/login', { replace: true });
    else if (companies.length === 0) navigate('/create-company', { replace: true });
    else navigate('/app?section=subscription', { replace: true });
  }, [isLoading, checked, user, companies.length, navigate]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-background">
      <Icon name="Loader2" className="animate-spin text-primary" size={32} />
    </div>
  );
};

export default PromoLinkPage;
