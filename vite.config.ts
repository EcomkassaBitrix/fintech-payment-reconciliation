import {defineConfig} from "vite";
import react from "@vitejs/plugin-react";
import {tanstackStart} from "@tanstack/react-start/plugin/vite";
import path from "path";
import {componentTagger} from "pp-tagger";

// Серверная половина hmr-keepalive (клиент — src/platform/dev-hmr.ts,
// подключается в src/routes/__root.tsx): после каждой рассылки и раз в 5-9 с
// шлём состояние «boot:seq», чтобы превью переживало обрывы сокета.
const hmrKeepalive = {
    name: 'hmr-ws-keepalive',
    apply: 'serve' as const,
    configureServer(server: any) {
        const boot = Date.now().toString(36);
        let seq = 0;
        const state = () => ({type: 'custom', event: 'ezst:hmr', data: `${boot}:${seq}`});
        const broadcast = server.ws.send.bind(server.ws);
        server.ws.send = (...args: any[]) => {
            seq++;
            broadcast(...args);
            broadcast(state());
        };
        server.ws.on('connection', (socket: any) => socket.send(JSON.stringify(state())));
        let timer: ReturnType<typeof setTimeout> | null = null;
        const tick = () => {
            broadcast(state());
            timer = setTimeout(tick, 5000 + Math.floor(Math.random() * 4000));
        };
        timer = setTimeout(tick, 5000 + Math.floor(Math.random() * 4000));
        server.httpServer?.on('close', () => {
            if (timer) clearTimeout(timer);
        });
    },
};

// https://tanstack.com/start/latest/docs/framework/react/guide/hosting
export default defineConfig(({command, mode}) => ({
    // Серверный бандл самодостаточен: зависимости вшиваются в
    // dist/server/server.js, на сервере node_modules не нужен. Только для
    // сборки: dev-сервер исполняет CJS-пакеты (react) из node_modules.
    ssr: command === 'build' ? {noExternal: true} : undefined,
    plugins: [
        // Тэггер первым: он размечает исходник до преобразований Start, иначе
        // номера строк в разметке сервера и клиента расходятся (hydration).
        mode === 'development' &&
        componentTagger(),
        // Компоненты маршрутов не выносим в отдельные модули: Start кладёт их
        // в src/routes/x.tsx?tsr-split=component, а тэггер модули с query
        // пропускает — визуальный редактор не видел JSX страниц. Пустой
        // список групп = ничего не выносить (autoCodeSplitting Start не даёт
        // выключить).
        tanstackStart({router: {codeSplittingOptions: {defaultBehavior: []}}}),
        react(),
        hmrKeepalive,
    ].filter(Boolean),
    resolve: {
        alias: {
            "@": path.resolve(import.meta.dirname, "./src"),
        },
    },
    // Start не пребандлит свои пакеты, и в dev роутер грузился ~120
    // отдельными модулями: долго на плохой сети, и любой сорванный запрос
    // ронял гидрацию. Библиотеки роутера (без виртуальных импортов Start)
    // собираем в .vite/deps — один экземпляр и для кода приложения, и для
    // сырых модулей Start.
    optimizeDeps: {
        include: [
            "@tanstack/react-router",
            "@tanstack/router-core",
            "@tanstack/router-core/isServer",
            "@tanstack/router-core/ssr/client",
            "@tanstack/history",
            "@tanstack/react-store",
            "seroval",
            "seroval-plugins/web",
            "cookie-es",
        ],
    },
    server: {
        // Маршруты преобразуются на старте vite, а не на первом заходе в превью.
        warmup: {
            clientFiles: ["./src/routes/**/*.tsx", "./src/router.tsx"],
            ssrFiles: ["./src/routes/**/*.tsx", "./src/router.tsx"],
        },
        host: '0.0.0.0',
        port: 5173,
        allowedHosts: true,
        hmr: {
            overlay: false,
            timeout: 7000, // pingInterval @vite/client — нужен <30s для DDoS Guard
        }
    },
}));
