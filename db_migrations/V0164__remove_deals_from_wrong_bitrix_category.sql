UPDATE t_p83864310_fintech_payment_reco.crm_deals
SET removed_at = NOW(), candidate_receipt_id = NULL
WHERE id IN (7, 18, 79) AND integration_id = 24 AND removed_at IS NULL;