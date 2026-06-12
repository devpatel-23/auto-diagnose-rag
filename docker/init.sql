-- docker/init.sql
-- -----------------
-- This file runs automatically the FIRST time the PostgreSQL container starts.
-- It enables the pgvector extension in our database.
--
-- WHY HERE?
-- The pgvector Docker image has the extension files installed,
-- but each database needs to explicitly activate it with CREATE EXTENSION.
-- We do it here so it's ready before our app connects.

-- Enable the pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Verify it installed correctly
-- (You'll see this in `docker-compose logs postgres`)
DO $$
BEGIN
    RAISE NOTICE 'pgvector extension enabled successfully';
END $$;
