import json
import os
from typing import Any, Optional, Tuple
from data_averis import loader
from classifier import classify_email
from reader import read_attachment
from extractor import  extract_shipment_details
from comparator import compare_shipments, TARGET_FIELDS
from dotenv import load_dotenv
load_dotenv()



# Category mapping — aligns internal classifier labels with the spec's enum values
CATEGORY_MAP = {
    "bl_comparison": "BL_COMPARISON",
    "si_request":    "SI_REQUEST",
    "invoice_query": "INVOICE_QUERY",
    "general":       "GENERAL",
    "spam":          "SPAM",
}


def get_attachment_paths(email_obj: Any) -> Tuple[Optional[str], Optional[str]]:
    """Safely parses attachment paths regardless of list or dict wrappers."""
    if not isinstance(email_obj, dict):
        return None, None

    attachments = email_obj.get("attachments")
    si_path, bl_path = None, None

    if isinstance(attachments, dict):
        si_path = attachments.get("si") or attachments.get("shipping_instruction")
        bl_path = attachments.get("bl") or attachments.get("bill_of_lading")

    elif isinstance(attachments, list):
        for item in attachments:
            if isinstance(item, dict):
                role = str(item.get("role") or item.get("type") or item.get("name") or "").lower()
                path = item.get("path") or item.get("filename") or item.get("file")
                if any(k in role for k in ["si", "shipping"]):
                    si_path = path
                elif any(k in role for k in ["bl", "lading"]):
                    bl_path = path
            elif isinstance(item, str):
                item_lower = item.lower()
                # Matches _si., _si_v1., si_doc, shipping_instruction, or ending with _si
                if any(pattern in item_lower for pattern in ["_si.", "_si_", "shipping_instruction", "/si_"]) or item_lower.endswith("_si"):
                    si_path = item
                elif any(pattern in item_lower for pattern in ["_bl.", "_bl_", "bill_of_lading", "/bl_"]) or item_lower.endswith("_bl"):
                    bl_path = item

    return si_path, bl_path


def process_email(email_raw: Any, data_dir: str) -> dict:
    # Handle cases where the email file JSON root is a list [ {...} ]
    if isinstance(email_raw, list) and len(email_raw) > 0:
        email = email_raw[0]
    elif isinstance(email_raw, dict):
        email = email_raw
    else:
        return {
            "category": "GENERAL",
            "status": "OK",
            "review_reason": None,
            "defect_fields": [],
            "has_defect": False
        }

    raw_cat = classify_email(email)
    category = CATEGORY_MAP.get(raw_cat.lower(), "GENERAL")

    record = {
        "category": category,
        "status": "OK",
        "review_reason": None,
        "defect_fields": [],
        "has_defect": False
    }

    if category != "BL_COMPARISON":
        return record

    si_rel_path, bl_rel_path = get_attachment_paths(email)

    if not si_rel_path or not bl_rel_path:
        record["status"] = "NEEDS_REVIEW"
        record["review_reason"] = "missing_attachment"
        return record

    si_full_path = os.path.join(data_dir, si_rel_path)
    bl_full_path = os.path.join(data_dir, bl_rel_path)

    try:
        si_text = read_attachment(si_full_path)
        bl_text = read_attachment(bl_full_path)
    except Exception as e:
        record["status"] = "NEEDS_REVIEW"
        record["review_reason"] = "unreadable"
        print(f"  [WARN] Attachment read failure: {e}")
        return record

    try:
        si_details = extract_shipment_details(si_text).model_dump()
        bl_details = extract_shipment_details(bl_text).model_dump()
    except Exception as e:
        record["status"] = "NEEDS_REVIEW"
        record["review_reason"] = "unreadable"
        print(f"  [WARN] Extraction failure: {e}")
        return record

    missing = [f for f in TARGET_FIELDS if si_details.get(f) is None or bl_details.get(f) is None]
    if missing:
        record["status"] = "NEEDS_REVIEW"
        record["review_reason"] = "missing_value"

    has_mismatch, mismatches = compare_shipments(si_details, bl_details)
    if has_mismatch:
        record["has_defect"] = True
        record["defect_fields"] = list(mismatches.keys())
        # Only set MISMATCH if we aren't already flagging for review
        if record["status"] == "OK":
            record["status"] = "MISMATCH"

    return record


def main():
    DATA_SOURCE = "data_averis"

    try:
        inbox = loader.Inbox(DATA_SOURCE)
        emails = list(inbox)
    except Exception as e:
        print(f"[ERROR] Error loading inbox from '{DATA_SOURCE}': {e}")
        return

    print(f"[INFO] Total emails loaded from '{DATA_SOURCE}': {len(emails)}")

    if len(emails) == 0:
        print(f"[ERROR] No emails found! Check if the folder path '{DATA_SOURCE}' is correct.")
        print("Expected folder structure:")
        print("  shipping_verifier/")
        print(f"  +-- {DATA_SOURCE}/")
        print("      +-- inbox/          (contains .json files)")
        print("      +-- attachments/    (contains document files)")
        return

    sample = emails[0]
    print(f"[DEBUG] First email keys: {list(sample.keys())}")

    sample_id = sample.get("email_id") or sample.get("id") or sample.get("message_id")
    print(f"[DEBUG] First email ID: {sample_id}")
    if sample_id is None:
        print("[ERROR] Email ID is None! Check key name from keys list above.")
        return

    results = {}
    print("\nRunning end-to-end processing...")

    for email in emails[:5]:


        

        email_id = email.get("email_id") or email.get("id") or email.get("message_id")

        if not email_id:
            print("[WARN] Skipped an email with missing ID")
            continue

        try:
            results[str(email_id)] = process_email(email, DATA_SOURCE)
            cat = results[str(email_id)]["category"]
            status = results[str(email_id)]["status"]
            print(f"  OK  {email_id}  [{cat}] [{status}]")
        except Exception as err:
            print(f"  FAIL {email_id}: {err}")

    # Save output formatted for self-evaluation
    with open("submission.json", "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved {len(results)} results to submission.json")


if __name__ == "__main__":
    main()
