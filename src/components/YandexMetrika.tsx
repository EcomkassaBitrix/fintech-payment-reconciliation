import { useEffect, useRef } from 'react';
import { useLocation } from "@/lib/router-compat";
import { setMetrikaCounter } from '@/lib/metrika';

type Ym = ((id: number, method: string, ...args: unknown[]) => void) & { a?: unknown[]; l?: number };

declare global {
  interface Window {
    ym?: Ym;
    dataLayer?: Record<string, unknown>[];
    __ymCounterId?: number;
  }
}

// Счётчик подключается в <head> (__root.tsx) ещё до загрузки приложения - так Вебвизор
// записывает визит с самого начала. Здесь только переходы между страницами (hit).
const YandexMetrika = () => {
  const location = useLocation();
  const firstRender = useRef(true);

  useEffect(() => {
    if (window.__ymCounterId) setMetrikaCounter(window.__ymCounterId);
  }, []);

  useEffect(() => {
    if (firstRender.current) {
      firstRender.current = false;
      return;
    }
    const id = window.__ymCounterId;
    if (id && window.ym) {
      window.ym(id, 'hit', window.location.href, { referer: document.referrer });
    }
  }, [location.pathname, location.search]);

  return null;
};

export default YandexMetrika;
