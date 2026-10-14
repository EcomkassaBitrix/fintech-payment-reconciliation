const CARDS = [
  { src: '/payments/mir.svg', alt: 'Мир' },
  { src: '/payments/visa.svg', alt: 'Visa' },
  { src: '/payments/mastercard.svg', alt: 'Mastercard' }
];

const PaymentLogos = ({ className = '' }: { className?: string }) => (
  <div className={`flex flex-wrap items-center gap-2 ${className}`}>
    {CARDS.map((c) => (
      <span key={c.alt} className="flex h-8 items-center rounded-md border border-border bg-white px-2.5">
        <img src={c.src} alt={c.alt} className="h-4 w-auto" loading="lazy" />
      </span>
    ))}
    <a
      href="https://www.tbank.ru/"
      target="_blank"
      rel="noopener noreferrer"
      title="АО «ТБанк» — tbank.ru"
      className="flex h-8 items-center rounded-md border border-border bg-white px-2.5"
    >
      <img src="/payments/tbank.svg" alt="Т‑Банк" className="h-5 w-auto" loading="lazy" />
    </a>
    <a
      href="https://www.tbank.ru/tpay/"
      target="_blank"
      rel="noopener noreferrer"
      title="T‑Pay — tbank.ru"
      className="flex h-8 items-center gap-1 rounded-md border border-border bg-white px-2.5 text-xs font-bold text-black"
    >
      <span className="flex h-4 w-4 items-center justify-center rounded-[3px] bg-[#FFDD2D] text-[10px] leading-none">T</span>
      Pay
    </a>
  </div>
);

export default PaymentLogos;
