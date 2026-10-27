import { useEffect, useState } from 'react';
import { useLocation, useNavigate } from "@/lib/router-compat";
import functionUrls from '../../backend/func2url.json';
import { DEFAULT_TRIAL_DAYS } from '@/lib/trialDays';
import { forgetTariff } from '@/lib/chosenTariff';
import type { Tariff } from '@/components/landing/PricingSection';
import LandingHeader from '@/components/landing/LandingHeader';
import HeroSection from '@/components/landing/HeroSection';
import PainsSection from '@/components/landing/PainsSection';
import FeaturesSection from '@/components/landing/FeaturesSection';
import HowItWorksSection from '@/components/landing/HowItWorksSection';
import { LandingCase, casesApi } from '@/components/cases/caseTypes';
import CasesSection from '@/components/landing/CasesSection';
import PricingSection from '@/components/landing/PricingSection';
import FaqSection from '@/components/landing/FaqSection';
import CtaSection from '@/components/landing/CtaSection';
import LandingFooter from '@/components/landing/LandingFooter';

const Landing = () => {
  const navigate = useNavigate();
  const [tariffs, setTariffs] = useState<Tariff[] | null>(null);

  // Тарифы и срок пробного периода - из настроек тарифов в админке.
  useEffect(() => {
    fetch(functionUrls['tariffs-list'])
      .then((res) => res.json())
      .then((data) => {
        if (data.success && data.tariffs?.length) setTariffs(data.tariffs);
      })
      .catch(() => {});
  }, []);

  const [cases, setCases] = useState<LandingCase[]>([]);

  useEffect(() => {
    fetch(`${casesApi}?public=1`)
      .then((res) => res.json())
      .then((data) => setCases(data.cases || []))
      .catch(() => {});
  }, []);

  const { hash } = useLocation();

  // Переход по ссылке вида /#pricing (например, «Сменить тариф») - прокручиваем к блоку.
  useEffect(() => {
    if (!hash) return;
    const timer = setTimeout(() => document.querySelector(hash)?.scrollIntoView({ behavior: 'smooth' }), 100);
    return () => clearTimeout(timer);
  }, [hash, tariffs, cases]);

  const trialTariff = tariffs?.find((t) => t.slug === 'trial');
  const trialDays = trialTariff?.trial_days || trialTariff?.period_days || DEFAULT_TRIAL_DAYS;

  // Общие кнопки «Попробовать бесплатно» - старт на тарифе «Пробный».
  const handleCtaClick = () => {
    forgetTariff();
    navigate('/login');
  };

  // Кнопка конкретного тарифа - он уже запомнен в PricingSection.
  const handleTariffClick = () => {
    navigate('/login');
  };

  return (
    <div className="min-h-screen bg-background">
      <LandingHeader onCtaClick={handleCtaClick} trialDays={trialDays} showCases={cases.length > 0} />
      <HeroSection onCtaClick={handleCtaClick} trialDays={trialDays} />
      <PainsSection />
      <FeaturesSection />
      <HowItWorksSection />
      <CasesSection cases={cases} />
      <PricingSection onCtaClick={handleTariffClick} trialDays={trialDays} tariffs={tariffs} />
      <CtaSection onCtaClick={handleCtaClick} trialDays={trialDays} />
      <FaqSection />
      <LandingFooter showCases={cases.length > 0} />
    </div>
  );
};

export default Landing;