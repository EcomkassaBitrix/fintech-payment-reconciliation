import functionUrls from '../../backend/func2url.json';

export const SESSION_KEY = 'ek_session';
const USER_KEY = 'ek_user';
const COMPANY_KEY = 'ek_current_company_id';
const PUBLIC_PATHS = ['/login', '/invite', '/'];

const projectUrls = Object.values(functionUrls as Record<string, string>);

export const getSessionToken = () => localStorage.getItem(SESSION_KEY);
export const setSessionToken = (token: string) => localStorage.setItem(SESSION_KEY, token);

export const clearSession = () => {
  localStorage.removeItem(SESSION_KEY);
  localStorage.removeItem(USER_KEY);
  localStorage.removeItem(COMPANY_KEY);
};

const isProjectFunction = (url: string) => projectUrls.some((base) => url.startsWith(base));

const isPublicPage = () => {
  const path = window.location.pathname;
  return path === '/' || PUBLIC_PATHS.some((p) => p !== '/' && path.startsWith(p));
};

let redirecting = false;

const RETRY_DELAYS_MS = [700, 1500, 3000];
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

// Кратковременная перегрузка базы («rate limit exceeded») или сбой шлюза
// функций. Шлюз при падении отвечает без CORS-заголовков, поэтому браузер
// видит это как обрыв сети («Load failed») - такие запросы тоже повторяем.
const isTransientResponse = async (response: Response) => {
  if ([502, 503, 504, 429].includes(response.status)) return true;
  if (response.status !== 500) return false;
  const text = await response.clone().text().catch(() => '');
  return /rate limit|QueryCanceled|timeout/i.test(text);
};

const fetchWithRetry = async (
  originalFetch: typeof fetch,
  input: RequestInfo | URL,
  init: RequestInit,
  canRetry: boolean
): Promise<Response> => {
  for (let attempt = 0; ; attempt++) {
    const last = !canRetry || attempt >= RETRY_DELAYS_MS.length || init.signal?.aborted;
    try {
      const response = await originalFetch(input, init);
      if (last || !(await isTransientResponse(response))) return response;
    } catch (error) {
      if (last || (error instanceof DOMException && error.name === 'AbortError')) throw error;
    }
    await sleep(RETRY_DELAYS_MS[attempt]);
  }
};

export const installSessionFetch = () => {
  const originalFetch = window.fetch.bind(window);

  window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
    if (!isProjectFunction(url)) return originalFetch(input, init);

    const token = getSessionToken();
    const headers = new Headers(init?.headers || (input instanceof Request ? input.headers : undefined));
    if (token && !headers.has('X-Session-Id')) headers.set('X-Session-Id', token);

    const method = (init?.method || (input instanceof Request ? input.method : 'GET')).toUpperCase();
    const response = await fetchWithRetry(originalFetch, input, { ...init, headers }, method === 'GET');

    if (response.status === 401 && !redirecting) {
      const data = await response.clone().json().catch(() => null);
      if (data?.error_code === 'session_required' && !isPublicPage()) {
        redirecting = true;
        clearSession();
        window.location.href = '/login';
      }
    }
    return response;
  };
};