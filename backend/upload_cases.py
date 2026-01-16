"""
Upload Demo Cases to Supabase
Run this script from the backend folder: python upload_cases.py
"""
import os
import sys
import json
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv()

from supabase import create_client

# Supabase connection
SUPABASE_URL = os.getenv("VITE_SUPABASE_URL")
SUPABASE_KEY = os.getenv("VITE_SUPABASE_ANON_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("❌ ERROR: Missing VITE_SUPABASE_URL or VITE_SUPABASE_ANON_KEY in .env")
    sys.exit(1)

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Path to cases folder
CASES_FOLDER = Path(__file__).parent.parent / "data" / "cases"

def upload_cases():
    """Read all case JSON files and insert into Supabase"""
    
    if not CASES_FOLDER.exists():
        print(f"❌ Folder not found: {CASES_FOLDER}")
        return
    
    case_files = list(CASES_FOLDER.glob("*.json"))
    print(f"📁 Found {len(case_files)} case files")
    
    for case_file in case_files:
        try:
            with open(case_file, 'r', encoding='utf-8') as f:
                case_data = json.load(f)
            
            # Map JSON structure to database columns
            db_record = {
                "case_number": case_data.get("case_number", case_data.get("case_id", "")),
                "case_type": case_data.get("case_type", ""),
                "court": case_data.get("court", ""),
                "status": case_data.get("status", "جاري"),
                "defendant_name": case_data.get("parties", {}).get("defendant", {}).get("full_name", ""),
                "plaintiff_name": case_data.get("parties", {}).get("victim", {}).get("full_name", ""),
                "charges": [c.get("charge", "") for c in case_data.get("charges", [])],
                "facts": case_data.get("facts", ""),
                "parties": case_data.get("parties", {}),
                "evidence": case_data.get("evidence", {}),
                "timeline": case_data.get("timeline", []),
                "defense_strategy": case_data.get("defense_strategy", {}),
                "notes": case_data.get("notes", ""),
                "source_file": case_file.name,
                "user_id": None  # Demo cases have no user (visible to all)
            }
            
            # Insert into Supabase
            result = supabase.table("cases").insert(db_record).execute()
            
            if result.data:
                print(f"✅ Uploaded: {case_file.name} -> ID: {result.data[0]['id']}")
            else:
                print(f"⚠️ No data returned for: {case_file.name}")
                
        except Exception as e:
            print(f"❌ Error uploading {case_file.name}: {e}")
    
    print("\n🎉 Done! Cases uploaded to Supabase.")

if __name__ == "__main__":
    upload_cases()
