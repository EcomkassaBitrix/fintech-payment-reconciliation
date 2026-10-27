CREATE TABLE IF NOT EXISTS t_p83864310_fintech_payment_reco.cron_run_history (
    id BIGSERIAL PRIMARY KEY,
    source VARCHAR(40) NOT NULL,
    company_id INTEGER NOT NULL,
    item_key VARCHAR(40) NOT NULL DEFAULT '',
    tick VARCHAR(40) NOT NULL,
    loaded INTEGER NOT NULL DEFAULT 0,
    error TEXT NULL,
    finished_at TIMESTAMP NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS cron_run_history_source_time_idx ON t_p83864310_fintech_payment_reco.cron_run_history (source, finished_at);
INSERT INTO t_p83864310_fintech_payment_reco.cron_run_history (source, company_id, item_key, tick, loaded, error, finished_at)
SELECT source, company_id, item_key, tick, loaded, error, finished_at
FROM t_p83864310_fintech_payment_reco.cron_source_runs
WHERE error IS DISTINCT FROM 'pending' AND finished_at > NOW() - INTERVAL '1 day';