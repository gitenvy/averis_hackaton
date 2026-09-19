import argparse
import json
import os
import io
import sys
from typing import Any, Optional, Tuple
import pandas as pd
from dotenv import load_dotenv

# ... (keep existing imports) ...

def main():
    # 1. Parse limit argument or environment variable
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="Limit number of emails to process")
    args, _ = parser.parse_known_args()

    limit = args.limit or int(os.getenv("BATCH_LIMIT", 0))

    DATA_SOURCE = os.getenv("EVAL_SERVER_URL", "http://localhost:8080")

    try:
        inbox = Inbox(DATA_SOURCE)
        emails = list(inbox)
        print(f"[INFO] Connected to Docker server at '{DATA_SOURCE}'. Total emails available: {len(emails)}")
    except Exception as e:
        print(f"[ERROR] Could not connect to Docker server at '{DATA_SOURCE}': {e}")
        return

    if len(emails) == 0:
        print("[ERROR] No emails returned from server!")
        return

    # Slice list if limit is set
    if limit > 0:
        emails = emails[:limit]
        print(f"[INFO] Sample limit applied: processing {len(emails)} emails.")

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

    # Save local submission copy
    with open("submission.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved {len(results)} results to submission.json")

    # POST results to server if connecting directly
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