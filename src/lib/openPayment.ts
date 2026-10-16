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
  try {
    window.top!.location.href = url;
    return true;
  } catch {
    return false;
  }
};
