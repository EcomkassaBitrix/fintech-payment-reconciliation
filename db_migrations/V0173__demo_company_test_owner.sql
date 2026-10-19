INSERT INTO t_p83864310_fintech_payment_reco.company_users (company_id, user_id, role_id, status, joined_at, created_at, updated_at)
SELECT 1, u.id, 2, 'active', NOW(), NOW(), NOW()
FROM t_p83864310_fintech_payment_reco.app_users u
WHERE u.phone = '79999999999'
  AND NOT EXISTS (SELECT 1 FROM t_p83864310_fintech_payment_reco.company_users cu WHERE cu.company_id = 1 AND cu.user_id = u.id);