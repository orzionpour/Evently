-- Down Migration: Drop all tables created in the up migration
DROP TABLE IF EXISTS job_attempts;
DROP TABLE IF EXISTS jobs;
DROP TABLE IF EXISTS events;
DROP TABLE IF EXISTS routes;