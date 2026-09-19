import json
import os
import io
import sys
from typing import Any, Optional, Tuple
import pandas as pd
from dotenv import load_dotenv

# Add 'data_averis' to path for loader import
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(BASE_DIR)
sys.path.append(os.path.join(BASE_DIR, "data_averis"))
sys.path.append(os.path.join(BASE_DIR, "data_averis", "server"))

from data_averis.server.loader import Inbox
from classifier import classify_email
from extractor import extract_shipment_details
from comparator import compare_shipments, TARGET_FIELDS

load_dotenv()

# Category mapping — aligns internal classifier labels with spec enum values
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
                if any(pattern in item_lower for pattern in ["_si.", "_si_", "shipping_instruction", "/si_"]) or item_lower.endswith("_si"):
                    si_path = item
                elif any(pattern in item_lower for pattern in ["_bl.", "_bl_", "bill_of_lading", "/bl_"]) or item_lower.endswith("_bl"):
                    bl_path = item

    return si_path, bl_path


def read_attachment_from_inbox(inbox: Inbox, rel_path: str) -> str:
    """Reads attachments over HTTP/local inbox, handling both plain text and .xlsx spreadsheets."""
    ext = os.path.splitext(rel_path)[1].lower()

    if ext == ".xlsx":
        raw_bytes = inbox.read_bytes(rel_path)
        excel_data = pd.read_excel(io.BytesIO(raw_bytes), sheet_name=None)
        output = []
        for sheet_name, df in excel_data.items():
            output.append(f"--- Sheet: {sheet_name} ---")
            output.append(df.to_csv(index=False))
        return "\n".join(output)
    
    return inbox.read_text(rel_path)


def process_email(email_raw: Any, inbox: Inbox) -> dict:
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
    category = CATEGORY_MAP.get(raw_cat.lower(), raw_cat.upper())

    record = {
        "category": category,
        "status": "OK",
        "review_reason": None,
        "defect_fields": [],
        "has_defect": False
    }

    # Non-comparison emails stop here
    if category != "BL_COMPARISON":
        return record

    # 1. Check for missing attachments
    si_rel_path, bl_rel_path = get_attachment_paths(email)
    if not si_rel_path or not bl_rel_path:
        record["status"] = "NEEDS_REVIEW"
        record["review_reason"] = "missing_attachment"
        return record

    # 2. Read attachment files
    try:
        si_text = read_attachment_from_inbox(inbox, si_rel_path)
        bl_text = read_attachment_from_inbox(inbox, bl_rel_path)
    except Exception as e:
        record["status"] = "NEEDS_REVIEW"
        record["review_reason"] = "unreadable"
        print(f"   [WARN] Attachment read failure: {e}")
        return record

    # Unreadable check if content is empty or corrupt
    if not si_text or not bl_text or len(si_text.strip()) < 10 or len(bl_text.strip()) < 10:
        record["status"] = "NEEDS_REVIEW"
        record["review_reason"] = "unreadable"
        return record

    # 3. Check for wrong_doc_type (e.g. attached file is an invoice or packing list)
    combined_docs = f"{si_text} {bl_text}".lower()
    if any(k in combined_docs for k in ["tax invoice", "commercial invoice", "packing list", "purchase order"]):
        if not any(k in combined_docs for k in ["bill of lading", "shipping instruction", "consignee", "port of loading"]):
            record["status"] = "NEEDS_REVIEW"
            record["review_reason"] = "wrong_doc_type"
            return record

    # 4. Extract entities from SI and BL
    try:
        si_details = extract_shipment_details(si_text, doc_type="SI")
        bl_details = extract_shipment_details(bl_text, doc_type="BL")
    except Exception as e:
        record["status"] = "NEEDS_REVIEW"
        record["review_reason"] = "unreadable"
        print(f"   [WARN] Extraction failure: {e}")
        return record

    # Safely handle dictionary conversion if required
   # ✅ REPLACE WITH THIS:
    si_dict = si_details
    bl_dict = bl_details

    # 5. Check for missing required target fields
    missing_fields = [
        f for f in TARGET_FIELDS 
        if si_dict.get(f) is None or bl_dict.get(f) is None
    ]
    if missing_fields:
        record["status"] = "NEEDS_REVIEW"
        record["review_reason"] = "missing_value"

    # 6. Compare extracted SI vs draft BL
    has_mismatch, mismatches = compare_shipments(si_dict, bl_dict)
    if has_mismatch:
        record["has_defect"] = True
        record["defect_fields"] = list(mismatches.keys())
        if record["status"] == "OK":
            record["status"] = "MISMATCH"

    return record


def main():
    DATA_SOURCE = os.getenv("EVAL_SERVER_URL", "http://localhost:8080")

    try:
        inbox = Inbox(DATA_SOURCE)
        emails = list(inbox)
        print(f"[INFO] Connected to Docker server at '{DATA_SOURCE}'. Total emails: {len(emails)}")
    except Exception as e:
        print(f"[ERROR] Could not connect to Docker server at '{DATA_SOURCE}': {e}")
        print("Make sure your Docker container is running on port 8080.")
        return

    if len(emails) == 0:
        print("[ERROR] No emails returned from server!")
        return

    results = {}
    print("\nRunning end-to-end processing...")

    for i, email in enumerate(emails, start=1):
        email_id = email.get("email_id") or email.get("id") or email.get("message_id")

        if not email_id:
            print(f"[{i}/{len(emails)}] [WARN] Skipped an email with missing ID")
            continue

        try:
            results[str(email_id)] = process_email(email, inbox)
            cat = results[str(email_id)]["category"]
            status = results[str(email_id)]["status"]
            print(f"[{i}/{len(emails)}] OK  {email_id}  [{cat}] [{status}]")
        except Exception as err:
            print(f"[{i}/{len(emails)}] FAIL {email_id}: {err}")

    # Save local submission file
    with open("submission.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved {len(results)} results to submission.json")

    # POST results to server and print evaluation scoreboard
    if inbox.is_http:
        print("\n[INFO] Submitting results to Docker server for evaluation...")
        try:
            scoreboard = inbox.submit(results)
            print("\n================ SCOREBOARD RESULTS ================")
            print(json.dumps(scoreboard, indent=2))
            print("====================================================\n")
        except Exception as e:
            print(f"[ERROR] Evaluation submission failed: {e}")


if __name__ == "__main__":
    main()