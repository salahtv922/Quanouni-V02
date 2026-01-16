-- SQL to update Audit Logs table

-- 1. Add the missing 'resource' column
ALTER TABLE public.audit_logs 
ADD COLUMN IF NOT EXISTS resource TEXT;

-- 2. Reload the schema cache so Supabase API (PostgREST) picks up the change
NOTIFY pgrst, 'reload schema';
