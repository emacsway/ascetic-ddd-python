-- Transactional Outbox Pattern - PostgreSQL Schema
--
-- Key Design Decisions:
-- 1. transaction_id (xid8) + position for correct ordering
-- 2. Visibility rule: only read committed transactions
-- 3. Consumer groups for multiple independent consumers
-- 4. FOR UPDATE locking for concurrent dispatcher safety

-- =============================================================================
-- OUTBOX TABLE
-- =============================================================================
-- Stores messages within the same transaction as business state changes.
-- Messages are only visible to dispatchers after the transaction commits.

CREATE TABLE IF NOT EXISTS outbox (
    -- Auto-incrementing position within the outbox
    -- Note: BIGSERIAL doesn't guarantee ordering in concurrent transactions!
    -- That's why we also capture transaction_id.
    "position" BIGSERIAL,

    -- Event type and version (for deserialization and routing)
    "event_type" VARCHAR(255) NOT NULL,
    "event_version" SMALLINT NOT NULL DEFAULT 1,

    -- Message payload (JSON-serialized)
    "payload" JSONB NOT NULL,

    -- Message metadata (must contain 'event_id' for idempotency)
    -- Also: correlation_id, causation_id, aggregate info, etc.
    "metadata" JSONB NOT NULL,

    -- Timestamp when the message was created
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- PostgreSQL transaction ID (xid8 type)
    -- Captured using pg_current_xact_id() at insert time
    -- Used for correct ordering across concurrent transactions
    "transaction_id" xid8 NOT NULL,

    -- Primary key: (transaction_id, position)
    -- This allows efficient queries for messages after a given position
    -- and ensures uniqueness within a transaction
    PRIMARY KEY ("transaction_id", "position")
);

-- Index for efficient queries by position alone (for simple sequential reads)
CREATE INDEX IF NOT EXISTS outbox_position_idx ON outbox ("position");

-- Index for queries filtering by event_type
CREATE INDEX IF NOT EXISTS outbox_event_type_idx ON outbox ("event_type");

-- Unique index on event_id from metadata for idempotency
-- Consumers should use metadata->>'event_id' to detect and ignore duplicates
CREATE UNIQUE INDEX IF NOT EXISTS outbox_event_id_uniq ON outbox (((metadata->>'event_id')::uuid));


-- =============================================================================
-- OUTBOX OFFSETS TABLE (Consumer Groups)
-- =============================================================================
-- Tracks the position of each consumer group in the outbox.
-- Supports multiple independent consumers reading the same outbox.

CREATE TABLE IF NOT EXISTS outbox_offsets (
    -- Consumer group identifier (empty string for default)
    "consumer_group" VARCHAR(255) NOT NULL,

    -- Last acknowledged offset
    -- Consumer has processed all messages up to and including this offset
    "offset_acked" BIGINT NOT NULL DEFAULT 0,

    -- Last processed transaction ID
    -- Used together with offset_acked to determine the exact position
    "last_processed_transaction_id" xid8 NOT NULL DEFAULT '0',

    -- Timestamp of last position update
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY ("consumer_group")
);


-- =============================================================================
-- USAGE NOTES
-- =============================================================================
--
-- PUBLISHING (within business transaction):
-- -----------------------------------------
-- INSERT INTO outbox (event_type, event_version, payload, metadata, transaction_id)
-- VALUES ($1, $2, $3, $4, pg_current_xact_id());
--
--
-- DISPATCHING (reading unprocessed messages):
-- -------------------------------------------
-- The key is to only read messages from COMMITTED transactions.
-- pg_snapshot_xmin(pg_current_snapshot()) returns the oldest transaction ID
-- that is still in progress. Any transaction_id below this is guaranteed
-- to be committed and visible.
--
-- WITH last_processed AS (
--     SELECT offset_acked, last_processed_transaction_id
--     FROM outbox_offsets
--     WHERE consumer_group = $1
--     FOR UPDATE  -- Lock to prevent concurrent reads
-- )
-- SELECT "position", transaction_id, event_type, event_version, payload, metadata
-- FROM outbox
-- WHERE (
--     (transaction_id = (SELECT last_processed_transaction_id FROM last_processed)
--      AND "position" > (SELECT offset_acked FROM last_processed))
--     OR
--     (transaction_id > (SELECT last_processed_transaction_id FROM last_processed))
-- )
-- AND transaction_id < pg_snapshot_xmin(pg_current_snapshot())
-- ORDER BY transaction_id ASC, "position" ASC
-- LIMIT 100;
--
--
-- ACKNOWLEDGING (updating consumer position):
-- -------------------------------------------
-- INSERT INTO outbox_offsets (consumer_group, offset_acked, last_processed_transaction_id, updated_at)
-- VALUES ($1, $2, $3, CURRENT_TIMESTAMP)
-- ON CONFLICT (consumer_group) DO UPDATE SET
--     offset_acked = EXCLUDED.offset_acked,
--     last_processed_transaction_id = EXCLUDED.last_processed_transaction_id,
--     updated_at = EXCLUDED.updated_at;
--
--
-- INITIALIZING CONSUMER GROUP:
-- ----------------------------
-- Before first dispatch, ensure the consumer group exists with zero position.
-- This is required for FOR UPDATE locking to work.
--
-- INSERT INTO outbox_offsets (consumer_group, offset_acked, last_processed_transaction_id)
-- VALUES ($1, 0, '0')
-- ON CONFLICT DO NOTHING;
--
--
-- CLEANUP (archiving old messages):
-- ---------------------------------
-- Find the minimum position across all consumer groups:
--
-- SELECT MIN(last_processed_transaction_id) as min_txid, MIN(offset_acked) as min_offset
-- FROM outbox_offsets;
--
-- Delete messages before that position:
--
-- DELETE FROM outbox
-- WHERE transaction_id < $min_txid
--    OR (transaction_id = $min_txid AND "position" <= $min_offset);
--
--
-- =============================================================================
-- WHY transaction_id (xid8)?
-- =============================================================================
--
-- Problem with SERIAL alone:
-- TX1 starts, gets position=1
-- TX2 starts, gets position=2
-- TX2 commits
-- Consumer reads position > 0, sees message 2
-- TX1 commits
-- Message 1 is now visible but consumer already moved past it!
--
-- Solution with transaction_id:
-- Only read messages where transaction_id < pg_snapshot_xmin(pg_current_snapshot())
-- This ensures we only see messages from fully committed transactions.
-- Within a transaction, messages are ordered by position.
-- Across transactions, they're ordered by transaction_id.
--
-- Reference: https://event-driven.io/en/ordering_in_postgres_outbox/
