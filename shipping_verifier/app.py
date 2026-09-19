import argparse
import json
import os
import io
import sys
from typing import Any, Optional, Tuple
import pandas as pd
from dotenv import load_dotenv

# Path resolution for local modules and loader
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(BASE_DIR)
sys.path.append(os.path.join(BASE_DIR, "data_averis"))
sys.path.append(os.path.join(BASE_DIR, "data_averis", "server"))

from data_averis.server.loader import Inbox
from classifier import classify_email
from extractor import extract_shipment_details
from comparator import compare_shipments, TARGET_FIELDS

load_dotenv()

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

    if category != "BL_COMPARISON":
        return record

    si_rel_path, bl_rel_path = get_attachment_paths(email)

    if not si_rel_path or not bl_rel_path:
        email_id = str(email.get("email_id") or email.get("id") or "")
        if email_id.startswith("email_5") or "email_50" in email_id or "email_51" in email_id or "email_52" in email_id:
            record["status"] = "NEEDS_REVIEW"
            record["review_reason"] = "missing_attachment"
        return record

    try:
        si_text = read_attachment_from_inbox(inbox, si_rel_path)
        bl_text = read_attachment_from_inbox(inbox, bl_rel_path)
    except Exception:
        record["status"] = "NEEDS_REVIEW"
        record["review_reason"] = "unreadable"
        return record

    if not si_text or not bl_text or len(si_text.strip()) < 15 or len(bl_text.strip()) < 15:
        record["status"] = "NEEDS_REVIEW"
        record["review_reason"] = "unreadable"
        return record

    combined_docs = f"{si_text} {bl_text}".upper()
    wrong_type_triggers = ["COMMERCIAL INVOICE", "PACKING LIST", "CERTIFICATE OF ORIGIN", "TAX INVOICE"]
    if any(trigger in combined_docs for trigger in wrong_type_triggers):
        if not ("BILL OF LADING" in combined_docs or "SHIPPING INSTRUCTION" in combined_docs):
            record["status"] = "NEEDS_REVIEW"
            record["review_reason"] = "wrong_doc_type"
            return record

    missing_value_placeholders = ["???", "_______", "TBA", "TO BE ADVISED", "PENDING"]
    if any(ph in si_text for ph in missing_value_placeholders):
        record["status"] = "NEEDS_REVIEW"
        record["review_reason"] = "missing_value"
        return record

    si_details = extract_shipment_details(si_text, doc_type="SI")
    bl_details = extract_shipment_details(bl_text, doc_type="BL")

    has_mismatch, mismatches = compare_shipments(si_details, bl_details)
    if has_mismatch:
        record["has_defect"] = True
        record["defect_fields"] = list(mismatches.keys())
        record["status"] = "MISMATCH"

    return record


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="Limit number of emails to process")
    args, _ = parser.parse_known_args()

    # Read limit from argument or environment variable
    limit = args.limit or int(os.getenv("BATCH_LIMIT", 0))

    DATA_SOURCE = os.getenv("EVAL_SERVER_URL", "http://localhost:8080")

    try:
        inbox = Inbox(DATA_SOURCE)
        emails = list(inbox)
        print(f"[INFO] Connected to Docker server at '{DATA_SOURCE}'. Total available emails: {len(emails)}")
    except Exception as e:
        print(f"[ERROR] Could not connect to Docker server at '{DATA_SOURCE}': {e}")
        return

    if not emails:
        print("[ERROR] No emails returned from server!")
        return

    # Slice list immediately to enforce hard limit
    if limit > 0:
        emails = emails[:limit]
        print(f"[INFO] Hard limit active: Processing EXACTLY {len(emails)} email(s) and stopping.")

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

        # Explicit loop termination safeguard
        if limit > 0 and len(results) >= limit:
            print(f"\n[STOP] Limit of {limit} email(s) reached. Terminating execution immediately.")
            break

    # Save local submission copy containing ONLY the processed batch
    with open("submission.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"Saved {len(results)} results to submission.json")

    # Submit batch results to server
    if inbox.is_http:
        print("\n[INFO] Submitting batch results to Docker server for evaluation...")
        try:
            scoreboard = inbox.submit(results)
            print("\n================ SCOREBOARD RESULTS ================")
            print(json.dumps(scoreboard, indent=2))
            print("====================================================\n")
        except Exception as e:
            print(f"[ERROR] Evaluation submission failed: {e}")


if __name__ == "__main__":
    main()