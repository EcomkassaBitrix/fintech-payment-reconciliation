// Служебный файл платформы. НЕ РЕДАКТИРОВАТЬ И НЕ УДАЛЯТЬ.
//
// Каждая публикация — отдельный релиз со своим серверным кодом. Вкладка,
// открытая до публикации, шлёт с вызовами серверных функций id своего
// релиза; на устаревший id сервер отвечает 409 + x-reload, и вкладка
// перезагружается вместо вызова функции, которой в новом релизе нет.
const BUILD_ID: string | undefined = import.meta.env.VITE_BUILD_ID;

export const buildIdFetch: typeof fetch = async (input, init) => {
    if (!BUILD_ID) return fetch(input, init);
    const headers = new Headers(init?.headers);
    headers.set("x-build-id", BUILD_ID);
    const response = await fetch(input, {...init, headers});
    if (response.status === 409 && response.headers.get("x-reload")) {
        window.location.reload();
        return new Promise<Response>(() => {});
    }
    return response;
};
