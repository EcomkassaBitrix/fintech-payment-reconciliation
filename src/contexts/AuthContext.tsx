import { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import functionUrls from '../../backend/func2url.json';
import { getSessionToken, setSessionToken, clearSession } from '@/lib/session';
import { GOALS, reachGoal } from '@/lib/metrika';

export interface Company {
  id: number;
  name: string;
  inn?: string | null;
  status: string;
  role_slug: string;
  role_name: string;
  role_color: string;
  subscription_status?: string;
  trial_ends_at?: string | null;
  current_period_end?: string | null;
  tariff_name?: string | null;
  tariff_slug?: string | null;
  max_users?: number | null;
  timezone?: string;
  role_modules?: string[];
  tariff_modules?: string[] | null;
  max_integrations?: number | null;
  max_automations?: number | null;
  platform_admin?: boolean;
  support_access?: boolean;
  support_access_until?: string | null;
  subscription_blocked?: boolean;
}

interface AuthUser {
  user_id: number;
  phone: string;
  full_name: string | null;
  email: string | null;
  is_platform_admin: boolean;
}

interface AuthContextValue {
  user: AuthUser | null;
  companies: Company[];
  currentCompany: Company | null;
  isLoading: boolean;
  isPlatformAdmin: boolean;
  cronEnabled: boolean;
  setCurrentCompanyId: (id: number) => void;
  requestCode: (phone: string, channel: string, purpose?: 'login' | 'invite') => Promise<void>;
  loginWithPhone: (phone: string, code: string, fullName?: string) => Promise<AuthUser>;
  refreshCompanies: (userId?: number) => Promise<void>;
  updateUser: (patch: Partial<Pick<AuthUser, 'full_name' | 'email'>>) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

const STORAGE_USER_KEY = 'ek_user';
const STORAGE_COMPANY_KEY = 'ek_current_company_id';

// Оплата тарифа: онлайн-оплаты нет, тариф проводит админка. Цель срабатывает у владельца,
// когда он видит активный платный период впервые (один раз на компанию и период).
const trackPaidTariffs = (list: Company[]) => {
  list.forEach((c) => {
    if (c.role_slug !== 'owner' || c.subscription_status !== 'active' || !c.current_period_end) return;
    const goal = c.tariff_slug === 'start' ? GOALS.paidStart : c.tariff_slug === 'business' ? GOALS.paidBusiness : null;
    if (!goal) return;
    const key = `ym_paid_${c.id}_${c.tariff_slug}_${c.current_period_end.slice(0, 10)}`;
    if (localStorage.getItem(key)) return;
    localStorage.setItem(key, '1');
    reachGoal(goal, { company_id: c.id });
  });
};

export const AuthProvider = ({ children }: { children: ReactNode }) => {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [cronEnabled, setCronEnabled] = useState(false);
  const [companies, setCompanies] = useState<Company[]>([]);
  const [currentCompanyId, setCurrentCompanyIdState] = useState<number | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_USER_KEY);
    if (stored && !getSessionToken()) {
      clearSession();
    } else if (stored) {
      try {
        const parsedUser: AuthUser = JSON.parse(stored);
        setUser(parsedUser);
        fetchCompanies(parsedUser.user_id).finally(() => setIsLoading(false));
        return;
      } catch {
        localStorage.removeItem(STORAGE_USER_KEY);
      }
    }
    setIsLoading(false);
  }, []);

  const fetchCompanies = async (userId: number) => {
    try {
      const res = await fetch(`${functionUrls['companies-list']}?user_id=${userId}`);
      const data = await res.json();
      if (res.ok && data.success) {
        setCompanies(data.companies || []);
        trackPaidTariffs(data.companies || []);
        setCronEnabled(Boolean(data.cron_enabled));

        const storedCompanyId = localStorage.getItem(STORAGE_COMPANY_KEY);
        const storedIdNum = storedCompanyId ? Number(storedCompanyId) : null;
        const exists = (data.companies || []).find((c: Company) => c.id === storedIdNum);

        if (exists) {
          setCurrentCompanyIdState(storedIdNum);
        } else if (data.companies && data.companies.length > 0) {
          setCurrentCompanyIdState(data.companies[0].id);
          localStorage.setItem(STORAGE_COMPANY_KEY, String(data.companies[0].id));
        } else {
          setCurrentCompanyIdState(null);
        }
      }
    } catch (error) {
      console.error('Failed to load companies:', error);
    }
  };

  const requestCode = async (phone: string, channel: string, purpose: 'login' | 'invite' = 'login') => {
    const res = await fetch(functionUrls['auth-phone'], {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'send', phone, channel, purpose })
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || !data.success) {
      throw new Error(data.error || 'Не удалось отправить код');
    }
  };

  const loginWithPhone = async (phone: string, code: string, fullName?: string): Promise<AuthUser> => {
    const res = await fetch(functionUrls['auth-phone'], {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'verify', phone, code, full_name: fullName })
    });
    const data = await res.json();

    if (!res.ok || !data.success) {
      throw new Error(data.error || 'Не удалось выполнить вход');
    }

    const authUser: AuthUser = {
      user_id: data.user_id,
      phone: data.phone,
      full_name: data.full_name,
      email: data.email,
      is_platform_admin: data.is_platform_admin
    };

    if (data.session_token) setSessionToken(data.session_token);
    if (data.is_new) reachGoal(GOALS.registration);
    setUser(authUser);
    localStorage.setItem(STORAGE_USER_KEY, JSON.stringify(authUser));
    setCompanies(data.companies || []);

    if (data.companies && data.companies.length > 0) {
      setCurrentCompanyIdState(data.companies[0].id);
      localStorage.setItem(STORAGE_COMPANY_KEY, String(data.companies[0].id));
    } else {
      setCurrentCompanyIdState(null);
      localStorage.removeItem(STORAGE_COMPANY_KEY);
    }

    return authUser;
  };

  useEffect(() => {
    if (!user?.user_id) return;
    const userId = user.user_id;
    const refresh = () => {
      if (document.visibilityState === 'visible') fetchCompanies(userId);
    };
    const timer = window.setInterval(refresh, 24 * 60 * 60 * 1000);
    document.addEventListener('visibilitychange', refresh);
    window.addEventListener('focus', refresh);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener('visibilitychange', refresh);
      window.removeEventListener('focus', refresh);
    };
  }, [user?.user_id]);

  // userId - сразу после входа, когда пользователь в состоянии ещё не обновился.
  const refreshCompanies = async (userId?: number) => {
    const id = userId ?? user?.user_id;
    if (id) {
      await fetchCompanies(id);
    }
  };

  const updateUser = (patch: Partial<Pick<AuthUser, 'full_name' | 'email'>>) => {
    setUser((prev) => {
      if (!prev) return prev;
      const next = { ...prev, ...patch };
      localStorage.setItem(STORAGE_USER_KEY, JSON.stringify(next));
      return next;
    });
  };

  const setCurrentCompanyId = (id: number) => {
    setCurrentCompanyIdState(id);
    localStorage.setItem(STORAGE_COMPANY_KEY, String(id));
  };

  const logout = () => {
    setUser(null);
    setCompanies([]);
    setCurrentCompanyIdState(null);
    const token = getSessionToken();
    clearSession();
    if (token) {
      fetch(functionUrls['auth-phone'], {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Session-Id': token },
        body: JSON.stringify({ action: 'logout' }),
        keepalive: true
      }).catch(() => undefined);
    }
    window.location.href = '/login';
  };

  const currentCompany = companies.find(c => c.id === currentCompanyId) || null;
  // Админка - только владельцу компании платформы и только когда выбрана эта компания.
  // Признак берём из свежего списка компаний: доступ, выданный после входа, появляется без перелогина.
  const isPlatformAdmin = Boolean(user && currentCompany?.platform_admin);

  return (
    <AuthContext.Provider
      value={{
        user,
        companies,
        currentCompany,
        isLoading,
        isPlatformAdmin,
        cronEnabled,
        setCurrentCompanyId,
        requestCode,
        loginWithPhone,
        refreshCompanies,
        updateUser,
        logout
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return ctx;
};