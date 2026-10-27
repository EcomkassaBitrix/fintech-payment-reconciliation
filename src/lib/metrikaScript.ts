import functionUrls from '../../backend/func2url.json';

export const FALLBACK_METRIKA_ID = '113249997';

export interface MetrikaConfig {
  id: string | null;
  inline: string[];
  srcs: string[];
  noscript: string;
}

const standardScript = (id: string) => `(function (m, e, t, r, i, k, a) {
    m[i] = m[i] || function () { (m[i].a = m[i].a || []).push(arguments) };
    m[i].l = 1 * new Date();
    for (var j = 0; j < document.scripts.length; j++) { if (document.scripts[j].src === r) { return; } }
    k = e.createElement(t), a = e.getElementsByTagName(t)[0], k.async = 1, k.src = r, a.parentNode.insertBefore(k, a)
})(window, document, "script", "https://mc.yandex.ru/metrika/tag.js?id=${id}", "ym");
ym(${id}, "init", { ssr: true, webvisor: true, clickmap: true, ecommerce: "dataLayer", referrer: document.referrer, url: location.href, accurateTrackBounce: true, trackLinks: true });`;

const prelude = (id: string | null) =>
  `window.dataLayer = window.dataLayer || [];${id ? ` window.__ymCounterId = ${Number(id)};` : ''}`;

// Разбирает код счётчика из админки на части для <head>: встроенные скрипты, внешние и <noscript>.
export const parseMetrika = (script: string | null, counterId: string | null): MetrikaConfig => {
  const code = (script || '').trim();
  if (!code) {
    const id = counterId && /^\d+$/.test(counterId) ? counterId : null;
    return { id, inline: id ? [prelude(id), standardScript(id)] : [], srcs: [], noscript: '' };
  }
  const id = code.match(/ym\(\s*(\d+)\s*,\s*['"]init/)?.[1] || counterId || null;
  const inline: string[] = [prelude(id)];
  const srcs: string[] = [];
  for (const m of code.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/gi)) {
    const src = m[1].match(/\bsrc\s*=\s*["']([^"']+)["']/i)?.[1];
    if (src) srcs.push(src);
    else if (m[2].trim()) inline.push(m[2]);
  }
  if (inline.length === 1 && !srcs.length) inline.push(code);
  const noscript = (code.match(/<noscript\b[^>]*>([\s\S]*?)<\/noscript>/i)?.[1] || '').trim();
  return { id, inline, srcs, noscript };
};

export const loadMetrika = async (): Promise<MetrikaConfig> => {
  try {
    const res = await fetch(`${(functionUrls as Record<string, string>)['platform-settings']}?public=1`);
    const data = await res.json();
    return parseMetrika(data.metrika_script || null, data.metrika_counter_id || null);
  } catch {
    return parseMetrika(null, FALLBACK_METRIKA_ID);
  }
};
