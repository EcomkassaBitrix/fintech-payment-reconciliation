UPDATE t_p83864310_fintech_payment_reco.company_users
SET status = 'removed', updated_at = NOW()
WHERE company_id = 1
  AND user_id = (SELECT id FROM t_p83864310_fintech_payment_reco.app_users WHERE phone = '79999999999');