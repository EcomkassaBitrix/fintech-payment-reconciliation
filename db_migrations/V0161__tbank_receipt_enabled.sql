UPDATE t_p83864310_fintech_payment_reco.platform_payment_providers
SET config = config
    || jsonb_build_object('receipt_enabled', true)
    || CASE WHEN config ? 'payment_method' THEN '{}'::jsonb ELSE '{"payment_method": "full_payment"}'::jsonb END
    || CASE WHEN config ? 'payment_object' THEN '{}'::jsonb ELSE '{"payment_object": "service"}'::jsonb END
    || CASE WHEN config ? 'ffd' THEN '{}'::jsonb ELSE '{"ffd": "1.2"}'::jsonb END
    || CASE WHEN config ? 'measurement_unit' THEN '{}'::jsonb ELSE '{"measurement_unit": "шт"}'::jsonb END,
    updated_at = NOW()
WHERE slug = 'tbank';
