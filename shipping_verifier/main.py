import argparse
import json
import os
import io
import sys
import time
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
import hackathonprototype as hp

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

    # Deterministic SI-vs-BL stage (handles txt/pdf/docx/xlsx, label matching, review reasons).
    decision, _details = hp.analyse_bl_comparison(inbox, email)
    record.update(decision)
    return record


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="Limit number of emails to process")
    args, _ = parser.parse_known_args()

    limit = args.limit or int(os.getenv("BATCH_LIMIT", 0))

    DATA_SOURCE = os.getenv("EVAL_SERVER_URL", "http://localhost:8080")
    
    emails = []
    inbox = None

    # 1. Try Docker evaluation server
    if DATA_SOURCE.startswith("http"):
        try:
            temp_inbox = Inbox(DATA_SOURCE)
            emails = list(temp_inbox)
            inbox = temp_inbox
            print(f"[INFO] Connected to Docker server at '{DATA_SOURCE}'. Total emails: {len(emails)}")
        except Exception as e:
            print(f"[WARN] Could not fetch from Docker server at '{DATA_SOURCE}': {e}")
            print("[INFO] Falling back to local offline folder...")

    # 2. Fallback to offline folder if server failed or wasn't used
    if not emails or inbox is None:
        possible_local_paths = [
            os.path.join(BASE_DIR, "offline_inbox"),
            os.path.join(os.path.dirname(BASE_DIR), "offline_inbox"),
            os.path.join(BASE_DIR, "data_averis"),
            os.path.join(os.path.dirname(BASE_DIR), "data_averis"),
        ]

        target_local_path = next((p for p in possible_local_paths if os.path.exists(p)), None)

        if target_local_path:
            try:
                inbox = Inbox(target_local_path)
                emails = list(inbox)
                print(f"[INFO] Plug-and-Play Mode: Loaded {len(emails)} emails from '{target_local_path}'.")
            except Exception as e:
                print(f"[ERROR] Could not load local dataset from '{target_local_path}': {e}")
                return
        else:
            print("[ERROR] Neither Docker server nor local offline_inbox/data_averis folders could be found!")
            return

    if not emails:
        print("[ERROR] No emails found in dataset!")
        return

    if limit > 0:
        emails = emails[:limit]
        print(f"[INFO] Processing EXACTLY {len(emails)} email(s) sequentially.")

    results = {}
    print("\nRunning sequential processing...")

    for i, email in enumerate(emails, start=1):
        email_id = str(email.get("email_id") or email.get("id") or email.get("message_id") or "")

        if not email_id:
            print(f"[{i}/{len(emails)}] [WARN] Skipped email with missing ID")
            continue

        try:
            res = process_email(email, inbox)
            results[email_id] = res
            cat = res["category"]
            status = res["status"]
            print(f"[{i}/{len(emails)}] OK  {email_id}  [{cat}] [{status}]")
        except Exception as err:
            print(f"[{i}/{len(emails)}] FAIL {email_id}: {err}")

        # Short pause between calls to respect free API rate limits
        time.sleep(0.3)

    submission_path = os.path.join(BASE_DIR, "submission.json")
    with open(submission_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved {len(results)} results to submission.json")

    if inbox and getattr(inbox, "is_http", False):
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