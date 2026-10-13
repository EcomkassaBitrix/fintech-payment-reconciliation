UPDATE t_p83864310_fintech_payment_reco.ecomkassa_payment_types SET provider_code = 'DOLYAME', updated_at = NOW()
WHERE id = 116 AND provider_code IS NULL
  AND NOT EXISTS (SELECT 1 FROM t_p83864310_fintech_payment_reco.ecomkassa_payment_types WHERE provider_code = 'DOLYAME');