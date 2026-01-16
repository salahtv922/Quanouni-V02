-- SAFE RLS FIX
-- 1. Drop the policy if it exists (to avoid "already exists" error)
DROP POLICY IF EXISTS "Enable insert for authenticated users only" ON public.audit_logs;

-- 2. Re-create the policy strictly allowing INSERT
CREATE POLICY "Enable insert for authenticated users only" 
ON public.audit_logs 
FOR INSERT 
TO authenticated 
WITH CHECK (true);

-- 3. Just in case, grant permission to the role used by the API
GRANT INSERT ON public.audit_logs TO authenticated;
GRANT INSERT ON public.audit_logs TO service_role;

NOTIFY pgrst, 'reload schema';
