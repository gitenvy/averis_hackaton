import json
import os
from data_averis import loader
from classifier import classify_email
from reader import read_attachment
from extractor import extract_shipment_details
from comparator import compare_shipments, TARGET_FIELDS
from dotenv import load_dotenv
load_dotenv()


# Category mapping to uppercase enums matching sample_submission.json
CATEGORY_MAP = {
    "document_comparison_request": "DOCUMENT_COMPARISON",
    "new_si_request": "NEW_SI",
    "invoice_query": "INVOICE",
    "general_message": "GENERAL",
    "spam": "SPAM",
}

def process_email(email: dict, data_dir: str) -> dict:
    raw_cat = classify_email(email)
    category = CATEGORY_MAP.get(raw_cat.lower(), raw_cat.upper())

    record = {
        "category": category,
        "status": "OK",
        "review_reason": None,
        "defect_fields": [],
        "has_defect": False
    }

    # Only document comparison requests proceed to attachment extraction
    if category not in ["DOCUMENT_COMPARISON", "DOCUMENT_COMPARISON_REQUEST"]:
        return record

    attachments = email.get("attachments", {})
    si_rel_path = attachments.get("si")
    bl_rel_path = attachments.get("bl")

    if not si_rel_path or not bl_rel_path:
        record["status"] = "NEEDS_REVIEW"
        record["review_reason"] = "Missing required SI or BL attachment reference."
        return record

    si_full_path = os.path.join(data_dir, si_rel_path)
    bl_full_path = os.path.join(data_dir, bl_rel_path)

    # Read attachments
    try:
        si_text = read_attachment(si_full_path)
        bl_text = read_attachment(bl_full_path)
    except Exception as e:
        record["status"] = "NEEDS_REVIEW"
        record["review_reason"] = f"Attachment read failure: {str(e)}"
        return record

    # Extract structured details via Gemini
    try:
        si_details = extract_shipment_details(si_text).model_dump()
        bl_details = extract_shipment_details(bl_text).model_dump()
    except Exception as e:
        record["status"] = "NEEDS_REVIEW"
        record["review_reason"] = f"Extraction failure: {str(e)}"
        return record

    # Escalate if required fields couldn't be extracted reliably
    missing = [f for f in TARGET_FIELDS if si_details.get(f) is None or bl_details.get(f) is None]
    if missing:
        record["status"] = "NEEDS_REVIEW"
        record["review_reason"] = f"Uncertain or unreadable fields: {', '.join(missing)}"

    # Compare fields
    has_mismatch, mismatches = compare_shipments(si_details, bl_details)
    
    if has_mismatch:
        record["has_defect"] = True
        record["defect_fields"] = list(mismatches.keys())

    return record

def main():
    DATA_SOURCE = "data_averis"  # Check if your folder is named "data" or "data_averis"
    
    try:
        inbox = loader.Inbox(DATA_SOURCE)
        emails = list(inbox)
    except Exception as e:
        print(f"❌ Error loading inbox from '{DATA_SOURCE}': {e}")
        return

    # --- DEBUG SECTION START ---
    print(f"🔍 DEBUG: Total emails loaded from '{DATA_SOURCE}': {len(emails)}")
    
    if len(emails) == 0:
        print(f"❌ DEBUG ALERT: No emails found! Check if the folder path '{DATA_SOURCE}' is correct.")
        print("Expected folder structure:")
        print("  shipping_verifier/")
        print(f"  └── {DATA_SOURCE}/")
        print("      ├── inbox/          (contains .json files)")
        print("      └── attachments/    (contains document files)")
        return

    sample = emails[0]
    print(f"🔍 DEBUG: First email dictionary keys: {list(sample.keys())}")
    
    sample_id = sample.get("id") or sample.get("email_id") or sample.get("message_id")
    print(f"🔍 DEBUG: First email extracted ID: {sample_id}")
    if sample_id is None:
        print("❌ DEBUG ALERT: Email ID is returning None! Check key name from keys list above.")
        return
    # --- DEBUG SECTION END ---

    results = {}
    print("\nRunning end-to-end processing...")

    for email in emails:
        email_id = email.get("id") or email.get("email_id") or email.get("message_id")
        
        # Guard against None key
        if not email_id:
            print("Warning: Skipped an email with missing ID")
            continue

        try:
            results[str(email_id)] = process_email(email, DATA_SOURCE)
            print(f"  ✓ Processed email {email_id}")
        except Exception as err:
            print(f"  ❌ Error processing email {email_id}: {err}")

    # Save output formatted for self-evaluation
    with open("submission.json", "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved {len(results)} results to submission.json")


if __name__ == "__main__":
    main()