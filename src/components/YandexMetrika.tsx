import { useEffect, useRef } from 'react';
import { useLocation } from "@/lib/router-compat";
import functionUrls from '../../backend/func2url.json';
import { setMetrikaCounter } from '@/lib/metrika';

type Ym = ((id: number, method: string, ...args: unknown[]) => void) & { a?: unknown[]; l?: number };

declare global {
  interface Window {
    ym?: Ym;
    dataLayer?: Record<string, unknown>[];
    __ymCounterId?: number;
  }
}

const api = (functionUrls as Record<string, string>)['platform-settings'];

// Счётчик Яндекс Метрики из настроек платформы: подключается при загрузке сайта,
// переходы между страницами приложения отправляются как просмотры (hit).
const YandexMetrika = () => {
  const location = useLocation();
  const counterRef = useRef<number | null>(null);

  useEffect(() => {
    fetch(`${api}?public=1`)
      .then((r) => r.json())
      .then((data) => {
        const id = Number(data.metrika_counter_id);
        if (!id) return;
        counterRef.current = id;
        if (!window.ym) {
          const ym: Ym = (...args: unknown[]) => {
            (ym.a = ym.a || []).push(args);
          };
          ym.l = Date.now();
          window.ym = ym;
        }
        // Как в официальном коде счётчика: tag.js?id=<номер> - сборка под настройки этого счётчика.
        const tagUrl = `https://mc.yandex.ru/metrika/tag.js?id=${id}`;
        if (!Array.from(document.scripts).some((s) => s.src === tagUrl)) {
          const script = document.createElement('script');
          script.async = true;
          script.src = tagUrl;
          const first = document.getElementsByTagName('script')[0];
          if (first?.parentNode) first.parentNode.insertBefore(script, first);
          else document.head.appendChild(script);
        }
        window.dataLayer = window.dataLayer || [];
        window.ym(id, 'init', {
          ssr: true,
          webvisor: true,
          clickmap: true,
          ecommerce: 'dataLayer',
          referrer: document.referrer,
          url: window.location.href,
          accurateTrackBounce: true,
          trackLinks: true
        });
        setMetrikaCounter(id);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (counterRef.current && window.ym) {
      window.ym(counterRef.current, 'hit', window.location.href);
    }
  }, [location.pathname, location.search]);

  return null;
};

export default YandexMetrika;
