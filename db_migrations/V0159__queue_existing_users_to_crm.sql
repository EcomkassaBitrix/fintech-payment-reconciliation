INSERT INTO t_p83864310_fintech_payment_reco.platform_crm_events (kind, user_id, payload)
SELECT 'register', u.id, '{"backfill": true}'::jsonb
FROM t_p83864310_fintech_payment_reco.app_users u
WHERE NOT EXISTS (SELECT 1 FROM t_p83864310_fintech_payment_reco.platform_crm_events e WHERE e.kind = 'register' AND e.user_id = u.id)
ORDER BY u.id;

INSERT INTO t_p83864310_fintech_payment_reco.platform_crm_events (kind, user_id, company_id, payload)
SELECT 'company', c.created_by, c.id, '{"backfill": true}'::jsonb
FROM t_p83864310_fintech_payment_reco.companies c
WHERE c.status = 'active' AND c.created_by IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM t_p83864310_fintech_payment_reco.platform_crm_events e WHERE e.kind = 'company' AND e.company_id = c.id)
ORDER BY c.id;
