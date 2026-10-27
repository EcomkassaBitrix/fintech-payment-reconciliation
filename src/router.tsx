import {createRouter} from "@tanstack/react-router";
import {QueryClient, QueryClientProvider} from "@tanstack/react-query";
import {routeTree} from "./routeTree.gen";
import NotFound from "@/components/NotFound";

// Новый роутер и QueryClient на каждый запрос: данные одного посетителя
// не должны попасть к другому.
export function getRouter() {
    const queryClient = new QueryClient();
    return createRouter({
        routeTree,
        scrollRestoration: true,
        defaultNotFoundComponent: NotFound,
        Wrap: ({children}) => (
            <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
        ),
    });
}

declare module "@tanstack/react-router" {
    interface Register {
        router: ReturnType<typeof getRouter>;
    }
}
