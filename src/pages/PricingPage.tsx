import { useNavigate } from '@/lib/router-compat';
import { DEFAULT_TRIAL_DAYS } from '@/lib/trialDays';
import { forgetTariff } from '@/lib/chosenTariff';
import type { Tariff } from '@/components/landing/PricingSection';
import LandingHeader from '@/components/landing/LandingHeader';
import PricingSection from '@/components/landing/PricingSection';
import FaqSection from '@/components/landing/FaqSection';
import CtaSection from '@/components/landing/CtaSection';
import LandingFooter from '@/components/landing/LandingFooter';

const PricingPage = ({ tariffs }: { tariffs: Tariff[] | null }) => {
  const navigate = useNavigate();
  const trialTariff = tariffs?.find((t) => t.slug === 'trial');
  const trialDays = trialTariff?.trial_days || trialTariff?.period_days || DEFAULT_TRIAL_DAYS;

  const handleCtaClick = () => {
    forgetTariff();
    navigate('/login');
  };

  return (
    <div className="min-h-screen bg-background">
      <LandingHeader onCtaClick={handleCtaClick} trialDays={trialDays} />
      <PricingSection asPage onCtaClick={() => navigate('/login')} trialDays={trialDays} tariffs={tariffs} />
      <FaqSection />
      <CtaSection onCtaClick={handleCtaClick} trialDays={trialDays} />
      <LandingFooter />
    </div>
  );
};

export default PricingPage;
