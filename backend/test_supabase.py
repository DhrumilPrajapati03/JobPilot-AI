import os
import sys

# Add backend directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from app.services.supabase import get_supabase_admin_client

supabase = get_supabase_admin_client()

tables = [
    "applications", 
    "job_applications", 
    "job_application", 
    "emails", 
    "cold_emails", 
    "hr_contacts", 
    "contacts",
    "user_profiles",
    "resumes",
    "tailored_resumes"
]

print("Checking tables:")
for table in tables:
    try:
        res = supabase.table(table).select("*").limit(1).execute()
        print(f"✅ Table '{table}' exists.")
    except Exception as e:
        # Check if the error is relation does not exist
        err_msg = str(e)
        if "relation" in err_msg and "does not exist" in err_msg:
            print(f"❌ Table '{table}' does NOT exist.")
        else:
            print(f"❓ Table '{table}' query returned error: {err_msg}")
