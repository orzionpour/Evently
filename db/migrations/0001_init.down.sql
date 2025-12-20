-- Down Migration: Drop all tables created in the up migration
DROP TABLE IF EXISTS job_attempt;
DROP TABLE IF EXISTS job;
DROP TABLE IF EXISTS event;
DROP TABLE IF EXISTS route;