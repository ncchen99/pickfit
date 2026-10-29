-- find_* rows: why the answer fell back to rules (the response's
-- degraded_reason), and what Meta returned. model_attempts is how many
-- requests were sent (2 = one retry after a transient error); model_statuses
-- is their HTTP statuses in order, e.g. [503, 200], with null where no
-- response came back (timeout, network).
ALTER TABLE events ADD COLUMN degraded_reason TEXT;
ALTER TABLE events ADD COLUMN model_attempts INTEGER CHECK (model_attempts IS NULL OR model_attempts >= 0);
ALTER TABLE events ADD COLUMN model_statuses TEXT CHECK (model_statuses IS NULL OR json_valid(model_statuses));
