-- TimescaleDB / PostgreSQL Initialization Script (Task L12)
-- Configures time-series hypertables, unique batch_id idempotency constraints, and indices.

-- 1. Enable TimescaleDB extension if running on TimescaleDB image
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;

-- 2. Periodic Telemetry Summaries Table
CREATE TABLE IF NOT EXISTS telemetry_summaries (
    id BIGSERIAL,
    batch_id UUID NOT NULL,
    device_id VARCHAR(32) NOT NULL,
    sector VARCHAR(8) NOT NULL,
    sent_at TIMESTAMPTZ NOT NULL,
    is_backfill BOOLEAN NOT NULL DEFAULT FALSE,
    interval_seconds REAL NOT NULL,
    peak_acceleration_g REAL NOT NULL,
    rms_acceleration_g REAL NOT NULL,
    sample_count INTEGER NOT NULL,
    temperature_c REAL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT pk_telemetry_summaries PRIMARY KEY (sent_at, batch_id)
);

-- Unique index on batch_id for idempotent deduplication (Task L14)
CREATE UNIQUE INDEX IF NOT EXISTS idx_summaries_batch_id ON telemetry_summaries (batch_id);
CREATE INDEX IF NOT EXISTS idx_summaries_device_time ON telemetry_summaries (device_id, sent_at DESC);
CREATE INDEX IF NOT EXISTS idx_summaries_sector_time ON telemetry_summaries (sector, sent_at DESC);

-- Convert to Timescale hypertable (if extension enabled)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
        PERFORM create_hypertable(
            'telemetry_summaries',
            'sent_at',
            if_not_exists => TRUE,
            chunk_time_interval => INTERVAL '1 day'
        );
    END IF;
END $$;

-- 3. Raw High-Resolution Event Waveforms Table
CREATE TABLE IF NOT EXISTS telemetry_waveforms (
    id BIGSERIAL,
    batch_id UUID NOT NULL,
    device_id VARCHAR(32) NOT NULL,
    sector VARCHAR(8) NOT NULL,
    sent_at TIMESTAMPTZ NOT NULL,
    is_backfill BOOLEAN NOT NULL DEFAULT FALSE,
    sampling_rate_hz INTEGER NOT NULL DEFAULT 1000,
    peak_acceleration_g REAL NOT NULL,
    rms_acceleration_g REAL NOT NULL,
    dominant_frequency_hz REAL NOT NULL,
    spectral_energy REAL NOT NULL,
    sample_count INTEGER NOT NULL,
    samples_json JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT pk_telemetry_waveforms PRIMARY KEY (sent_at, batch_id)
);

-- Unique index on batch_id for idempotent deduplication (Task L14)
CREATE UNIQUE INDEX IF NOT EXISTS idx_waveforms_batch_id ON telemetry_waveforms (batch_id);
CREATE INDEX IF NOT EXISTS idx_waveforms_device_time ON telemetry_waveforms (device_id, sent_at DESC);
CREATE INDEX IF NOT EXISTS idx_waveforms_sector_time ON telemetry_waveforms (sector, sent_at DESC);

-- Convert to Timescale hypertable (if extension enabled)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
        PERFORM create_hypertable(
            'telemetry_waveforms',
            'sent_at',
            if_not_exists => TRUE,
            chunk_time_interval => INTERVAL '1 day'
        );
    END IF;
END $$;

-- 4. Multi-Node Correlated Seismic Events Table (Task L15)
CREATE TABLE IF NOT EXISTS seismic_events (
    id BIGSERIAL PRIMARY KEY,
    detected_at TIMESTAMPTZ NOT NULL,
    sector VARCHAR(8) NOT NULL,
    triggering_nodes_count INTEGER NOT NULL,
    max_peak_g REAL NOT NULL,
    estimated_magnitude REAL NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_events_time ON seismic_events (detected_at DESC);
