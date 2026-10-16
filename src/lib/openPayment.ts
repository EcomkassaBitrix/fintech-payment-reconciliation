export const isEmbedded = () => {
  try {
    return window.self !== window.top;
  } catch {
    return true;
  }
};

export const preparePaymentWindow = (): Window | null => (isEmbedded() ? window.open('', '_blank') : null);

export const openPaymentPage = (url: string, prepared?: Window | null): boolean => {
  if (!isEmbedded()) {
    window.location.href = url;
    return true;
  }
  if (prepared && !prepared.closed) {
    prepared.location.href = url;
    return true;
  }
  const tab = window.open(url, '_blank');
  return tab !== null;
};
