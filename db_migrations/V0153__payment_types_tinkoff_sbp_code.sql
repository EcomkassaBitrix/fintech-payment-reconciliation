UPDATE t_p83864310_fintech_payment_reco.ecomkassa_payment_types SET provider_code = 'TINKOFF_BANK_SBP', updated_at = NOW()
WHERE id = 111 AND provider_code IS NULL
  AND NOT EXISTS (SELECT 1 FROM t_p83864310_fintech_payment_reco.ecomkassa_payment_types WHERE provider_code = 'TINKOFF_BANK_SBP');