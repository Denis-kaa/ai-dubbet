-- Per-job audio output selection.
-- Existing rows remain compatible: NULL means the configured application default.
ALTER TABLE dubbing_jobs
    ADD COLUMN IF NOT EXISTS audio_mix_mode VARCHAR(20);

-- Only recognized values are allowed when explicitly stored.
ALTER TABLE dubbing_jobs
    DROP CONSTRAINT IF EXISTS ck_dubbing_jobs_audio_mix_mode;

ALTER TABLE dubbing_jobs
    ADD CONSTRAINT ck_dubbing_jobs_audio_mix_mode
    CHECK (audio_mix_mode IS NULL OR audio_mix_mode IN ('dubbed_only', 'ducked_mix'));
