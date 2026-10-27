// Совместимость с react-router-dom поверх TanStack Router: старые страницы
// продолжают импортировать Link/useNavigate/useParams/useLocation, меняется
// только строка импорта. Новый код пишем на API TanStack напрямую.
import {forwardRef, type AnchorHTMLAttributes, type ReactNode} from "react";
import {
    Link as TsLink,
    Navigate as TsNavigate,
    useLocation as useTsLocation,
    useParams as useTsParams,
    useRouter,
} from "@tanstack/react-router";

type To = string | {pathname?: string; search?: string; hash?: string};

function splitTo(to: To): {to: string; search?: Record<string, string>; hash?: string} {
    const raw = typeof to === "string" ? to : `${to.pathname ?? ""}${to.search ?? ""}${to.hash ?? ""}`;
    const [beforeHash, hash] = raw.split("#");
    const [path, query] = beforeHash.split("?");
    const search = query ? Object.fromEntries(new URLSearchParams(query)) : undefined;
    return {to: path || ".", search, hash: hash || undefined};
}

type LinkProps = Omit<AnchorHTMLAttributes<HTMLAnchorElement>, "href"> & {
    to: To;
    replace?: boolean;
    state?: unknown;
    children?: ReactNode;
};

export const Link = forwardRef<HTMLAnchorElement, LinkProps>(({to, replace, state: _state, ...rest}, ref) => {
    const target = splitTo(to);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    return <TsLink ref={ref} {...(rest as any)} to={target.to as any} search={target.search as any} hash={target.hash} replace={replace}/>;
});
Link.displayName = "Link";

type NavLinkProps = Omit<LinkProps, "className" | "children"> & {
    className?: string | ((s: {isActive: boolean}) => string);
    children?: ReactNode | ((s: {isActive: boolean}) => ReactNode);
    end?: boolean;
};

export const NavLink = forwardRef<HTMLAnchorElement, NavLinkProps>(({className, children, end, to, ...rest}, ref) => {
    const {pathname} = useTsLocation();
    const path = splitTo(to).to;
    const isActive = end ? pathname === path : pathname === path || pathname.startsWith(path.endsWith("/") ? path : path + "/");
    return (
        <Link ref={ref} to={to} {...rest} className={typeof className === "function" ? className({isActive}) : className}>
            {typeof children === "function" ? children({isActive}) : children}
        </Link>
    );
});
NavLink.displayName = "NavLink";

export function useNavigate() {
    const router = useRouter();
    return (to: To | number, options?: {replace?: boolean; state?: unknown}) => {
        if (typeof to === "number") return router.history.go(to);
        const target = splitTo(to);
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        return router.navigate({to: target.to as any, search: target.search as any, hash: target.hash, replace: options?.replace});
    };
}

export function useParams<T extends Record<string, string | undefined> = Record<string, string | undefined>>(): T {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    return useTsParams({strict: false} as any) as T;
}

export function useLocation() {
    const location = useTsLocation();
    return {
        pathname: location.pathname,
        search: location.searchStr,
        hash: location.hash ? `#${location.hash}` : "",
        state: location.state as unknown,
        key: location.state?.__TSR_key ?? "default",
    };
}

export function useSearchParams(): [URLSearchParams, (next: URLSearchParams | Record<string, string>, opts?: {replace?: boolean}) => void] {
    const location = useTsLocation();
    const router = useRouter();
    const params = new URLSearchParams(location.searchStr);
    const set = (next: URLSearchParams | Record<string, string>, opts?: {replace?: boolean}) => {
        const qs = new URLSearchParams(next as Record<string, string>).toString();
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        router.navigate({to: location.pathname as any, search: Object.fromEntries(new URLSearchParams(qs)) as any, replace: opts?.replace});
    };
    return [params, set];
}

export function Navigate({to, replace}: {to: To; replace?: boolean}) {
    const target = splitTo(to);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    return <TsNavigate to={target.to as any} search={target.search as any} hash={target.hash} replace={replace}/>;
}
