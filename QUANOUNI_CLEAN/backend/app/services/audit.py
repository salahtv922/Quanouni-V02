from app.services.database import get_supabase
from datetime import datetime
import asyncio

class AuditService:
    @staticmethod
    async def log_action(
        user_id: str,
        username: str,
        action: str,
        details: dict = None,
        resource: str = None,
        ip_address: str = None
    ):
        """
        Logs an action to the audit_logs table.
        This function should ideally be fire-and-forget or async to not block the main request.
        """
        try:
            supabase = get_supabase()
            
            # Handle legacy/demo user ID which is not a valid UUID
            if user_id == "legacy_id":
                user_id = None # Set to None for DB or use a specific NIL UUID if strictly required

            payload = {
                "user_id": user_id,
                "username": username,
                "action": action,
                "details": details or {},
                "resource": resource,
                "ip_address": ip_address,
                # "timestamp": datetime.utcnow().isoformat()  <-- Let DB handle created_at via DEFAULT or use created_at key
                "created_at": datetime.utcnow().isoformat()
            }
            
            # Using fire-and-forget approach or ensure it awaits depending on critical nature
            # For now, we await it to ensure it's written, but can be backgrounded.
            data = supabase.table("audit_logs").insert(payload).execute()
            return data
            
        except Exception as e:
            # RLS Policy violations are common in dev/anon mode, don't spam terminal
            error_msg = str(e)
            if "42501" in error_msg or "violates row-level security" in error_msg:
                pass # Silently ignore RLS errors for now
            else:
                print(f"[AUDIT LOG WARNING] Could not log action '{action}': {e}")
            return None

audit_service = AuditService()
