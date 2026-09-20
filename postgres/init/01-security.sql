-- Dedicated cluster only: never host unrelated production databases here.
REVOKE ALL ON DATABASE postgres FROM PUBLIC;
REVOKE ALL ON DATABASE template1 FROM PUBLIC;
-- New databases are created by the control plane and immediately locked down.
