// Платёжная страница банка не открывается внутри чужой страницы (окно предпросмотра редактора) -
// в этом случае открываем её в новой вкладке. Возвращает false, если браузер заблокировал вкладку.
export const isEmbedded = () => {
  try {
    return window.self !== window.top;
  } catch {
    return true;
  }
};

export const openPaymentPage = (url: string): boolean => {
  if (!isEmbedded()) {
    window.location.href = url;
    return true;
  }
  const tab = window.open(url, '_blank', 'noopener');
  return tab !== null;
};
