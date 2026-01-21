-- OPEN AUDIT LOGS POLICY
-- Allow both 'anon' (backend) and 'authenticated' users to insert logs.

-- 1. Drop old restrictive policy
DROP POLICY IF EXISTS "Enable insert for authenticated users only" ON public.audit_logs;
DROP POLICY IF EXISTS "Enable insert for all (anon + auth)" ON public.audit_logs;

-- 2. Create correct broad policy
CREATE POLICY "Enable insert for all (anon + auth)" 
ON public.audit_logs 
FOR INSERT 
TO anon, authenticated 
WITH CHECK (true);

-- 3. Grant necessary permissions
GRANT INSERT ON public.audit_logs TO anon;
GRANT INSERT ON public.audit_logs TO authenticated;
GRANT INSERT ON public.audit_logs TO service_role;

NOTIFY pgrst, 'reload schema';
