import type {ReactNode} from "react";
import {HeadContent, Outlet, Scripts, createRootRoute} from "@tanstack/react-router";
import {QueryClient, QueryClientProvider} from "@tanstack/react-query";
import {useState} from "react";
import {Toaster} from "@/components/ui/toaster";
import {Toaster as Sonner} from "@/components/ui/sonner";
import {TooltipProvider} from "@/components/ui/tooltip";
import {AuthProvider} from "@/contexts/AuthContext";
import {BackfillProvider} from "@/contexts/BackfillContext";
import MaintenanceGate from "@/components/MaintenanceGate";
import YandexMetrika from "@/components/YandexMetrika";
import PendingPromoActivator from "@/components/PendingPromoActivator";
import NotFoundPage from "@/pages/NotFoundPage";
import {installSessionFetch} from "@/lib/session";
import {PLATFORM_META, PLATFORM_SCRIPTS} from "@/platform/scripts.gen";
import {HMR_CLIENT} from "@/platform/dev-hmr";
import appCss from "@/index.css?url";

// Browser only: adds the session header to calls of project functions before any component fetches.
if (typeof window !== "undefined") installSessionFetch();

const TITLE = "Сверка - электронный бухгалтер";
const DESCRIPTION = "Сверяет все платежи с чекам без вашего участия. ";
const OG_IMAGE = "https://cdn.poehali.dev/projects/***/files/og-image-1791745310357.png";
const FAVICON = "https://cdn.poehali.dev/projects/***/files/favicon-1790957337649.jpg";

const METRIKA_ID = 113249997;
const METRIKA = `(function (m, e, t, r, i, k, a) {
    m[i] = m[i] || function () { (m[i].a = m[i].a || []).push(arguments) };
    m[i].l = 1 * new Date();
    for (var j = 0; j < document.scripts.length; j++) { if (document.scripts[j].src === r) { return; } }
    k = e.createElement(t), a = e.getElementsByTagName(t)[0], k.async = 1, k.src = r, a.parentNode.insertBefore(k, a)
})(window, document, "script", "https://mc.yandex.ru/metrika/tag.js?id=${METRIKA_ID}", "ym");
window.dataLayer = window.dataLayer || [];
window.__ymCounterId = ${METRIKA_ID};
ym(${METRIKA_ID}, "init", { ssr: true, webvisor: true, clickmap: true, ecommerce: "dataLayer", referrer: document.referrer, url: location.href, accurateTrackBounce: true, trackLinks: true });`;

export const Route = createRootRoute({
    head: () => ({
        meta: [
            {charSet: "utf-8"},
            {name: "viewport", content: "width=device-width, initial-scale=1.0"},
            {name: "yandex-verification", content: "5bcb954625e73d3e"},
            {title: TITLE},
            {name: "description", content: DESCRIPTION},
            {name: "author", content: "poehali.dev"},
            {property: "og:title", content: TITLE},
            {property: "og:description", content: DESCRIPTION},
            {property: "og:image", content: OG_IMAGE},
            {property: "og:image:width", content: "4800"},
            {property: "og:image:height", content: "2520"},
            {property: "og:image:alt", content: "Поехали! — сервис разработки сайтов с помощью ИИ"},
            {name: "twitter:image", content: OG_IMAGE},
            ...PLATFORM_META,
        ],
        links: [
            {rel: "stylesheet", href: appCss},
            {rel: "icon", type: "image/jpg", href: FAVICON},
        ],
        // IMPORTANT: DO NOT REMOVE PLATFORM SCRIPTS AND THE DEV HMR CLIENT!
        scripts: [
            ...(import.meta.env.DEV ? [{children: HMR_CLIENT}] : []),
            ...PLATFORM_SCRIPTS,
            {children: METRIKA},
        ],
    }),
    component: RootComponent,
    notFoundComponent: NotFoundPage,
});

function RootComponent() {
    const [queryClient] = useState(() => new QueryClient());
    return (
        <RootDocument>
            <QueryClientProvider client={queryClient}>
                <TooltipProvider>
                    <Toaster/>
                    <Sonner/>
                    <YandexMetrika/>
                    <AuthProvider>
                        <BackfillProvider>
                            <MaintenanceGate>
                                <PendingPromoActivator/>
                                <Outlet/>
                            </MaintenanceGate>
                        </BackfillProvider>
                    </AuthProvider>
                </TooltipProvider>
            </QueryClientProvider>
        </RootDocument>
    );
}

function RootDocument({children}: { children: ReactNode }) {
    return (
        <html lang="ru">
        <head>
            <HeadContent/>
        </head>
        <body>
        {children}
        <Scripts/>
        </body>
        </html>
    );
}