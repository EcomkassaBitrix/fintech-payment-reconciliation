// Служебный файл платформы: подключается в src/routes/__root.tsx.
// Платформа перезаписывает его сама. НЕ РЕДАКТИРОВАТЬ И НЕ УДАЛЯТЬ.
export const PLATFORM_META: {name: string; content: string; value: string}[] = [
    {name: "pp-name", content: "fintech-payment-reconciliation", value: "fintech-payment-reconciliation"},
];

export const PLATFORM_SCRIPTS: {src: string; defer?: boolean}[] = [
    {src: "https://cdn.poehali.dev/intertnal/js/pp-min-2.js"},
    {src: "https://cdn.poehali.dev/intertnal/js/route-min.js"},
    {src: "https://cdn.poehali.dev/intertnal/js/telemetry-min.js"},
    {src: "https://cdn.poehali.dev/intertnal/js/ve.min.js", defer: true},
];
