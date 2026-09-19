import json
import re
from typing import Any, Dict, List, Optional, Tuple
from data_averis import loader

# The 7 required fields to compare
TARGET_FIELDS = [
    "shipper",
    "consignee",
    "notify_party",
    "port_of_loading",
    "port_of_discharge",
    "container_count",
    "gross_weight_kg",
]


def classify_email(email: Dict[str, Any]) -> str:
    """
    Classifies email into one of:
    - document_comparison_request
    - new_si_request
    - invoice_query
    - general_message
    - spam
    """
    subject = email.get("subject", "").lower()
    body = email.get("body", "").lower()
    content = f"{subject} {body}"

    if any(k in content for k in ["casino", "lottery", "unsubscribed", "buy now"]):
        return "spam"
    if any(k in content for k in ["invoice", "billing", "payment", "receipt"]):
        return "invoice_query"
    if any(k in content for k in ["new si", "create si", "shipping instruction request"]):
        return "new_si_request"
    if any(k in content for k in ["compare", "draft bl", "check bl", "verify", "si vs bl"]):
        return "document_comparison_request"

    # Fallback default
    return "general_message"


def parse_document_text(text: str) -> Dict[str, Any]:
    """
    Extracts key shipment fields from raw text using regex patterns.
    Can be swapped or augmented with an LLM for complex/scanned formats.
    """
    data = {}

    # Extract Shipper
    shipper_match = re.search(r"(?:Shipper|Exporter):\s*(.*)", text, re.IGNORECASE)
    data["shipper"] = shipper_match.group(1).strip() if shipper_match else None

    # Extract Consignee
    consignee_match = re.search(r"(?:Consignee):\s*(.*)", text, re.IGNORECASE)
    data["consignee"] = consignee_match.group(1).strip() if consignee_match else None

    # Extract Notify Party
    notify_match = re.search(r"(?:Notify Party|Notify):\s*(.*)", text, re.IGNORECASE)
    data["notify_party"] = notify_match.group(1).strip() if notify_match else None

    # Extract Port of Loading (POL)
    pol_match = re.search(r"(?:Port of Loading|POL|Load Port):\s*(.*)", text, re.IGNORECASE)
    data["port_of_loading"] = pol_match.group(1).strip() if pol_match else None

    # Extract Port of Discharge (POD)
    pod_match = re.search(r"(?:Port of Discharge|POD|Discharge Port):\s*(.*)", text, re.IGNORECASE)
    data["port_of_discharge"] = pod_match.group(1).strip() if pod_match else None

    # Extract Container Count
    container_match = re.search(r"(?:Container Count|Total Containers|Containers):\s*(\d+)", text, re.IGNORECASE)
    data["container_count"] = int(container_match.group(1)) if container_match else None

    # Extract Gross Weight (kg)
    weight_match = re.search(r"(?:Gross Weight|GW|Weight):\s*([\d,\.]+)\s*(?:kg|kgs)?", text, re.IGNORECASE)
    if weight_match:
        clean_w = weight_match.group(1).replace(",", "")
        try:
            data["gross_weight_kg"] = float(clean_w)
        except ValueError:
            data["gross_weight_kg"] = None
    else:
        data["gross_weight_kg"] = None

    return data


def normalize_val(field: str, val: Any) -> Optional[str]:
    """Standardizes string and numeric formats for comparison."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return str(val)
    # Strip spaces and case for textual comparison
    return re.sub(r"\s+", " ", str(val)).strip().lower()


def compare_documents(si_data: Dict[str, Any], bl_data: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    """Compares SI and BL data across the 7 fields."""
    mismatches = {}
    has_mismatch = False

    for field in TARGET_FIELDS:
        si_val = si_data.get(field)
        bl_val = bl_data.get(field)

        norm_si = normalize_val(field, si_val)
        norm_bl = normalize_val(field, bl_val)

        if norm_si != norm_bl:
            has_mismatch = True
            mismatches[field] = {
                "si": si_val,
                "bl": bl_val
            }

    return has_mismatch, mismatches


def process_inbox(data_source: str = "data") -> Dict[str, Any]:
    """Main execution loop to process all emails and generate the submission dict."""
    inbox = loader.Inbox(data_source)
    results = {}

    for email in inbox:
        email_id = email.get("id") or email.get("email_id")
        category = classify_email(email)

        record = {
            "category": category,
            "has_mismatch": False,
            "mismatches": {},
            "needs_human_review": False,
            "review_reason": None
        }

        if category == "document_comparison_request":
            si_path = email.get("attachments", {}).get("si")
            bl_path = email.get("attachments", {}).get("bl")

            if not si_path or not bl_path:
                record["needs_human_review"] = True
                record["review_reason"] = "Missing required SI or BL attachment."
            else:
                try:
                    si_text = inbox.read_text(si_path)
                    bl_text = inbox.read_text(bl_path)

                    si_data = parse_document_text(si_text)
                    bl_data = parse_document_text(bl_text)

                    # Check for missing critical fields
                    if any(si_data[f] is None for f in TARGET_FIELDS) or any(bl_data[f] is None for f in TARGET_FIELDS):
                        record["needs_human_review"] = True
                        record["review_reason"] = "Failed to parse one or more target fields reliably."

                    has_mismatch, mismatches = compare_documents(si_data, bl_data)
                    record["has_mismatch"] = has_mismatch
                    record["mismatches"] = mismatches

                except Exception as e:
                    record["needs_human_review"] = True
                    record["review_reason"] = f"Extraction error: {str(e)}"

        results[email_id] = record

    return results


if __name__ == "__main__":
    # Point to local folder 'data' or local server URL 'http://localhost:8080'
    DATA_SOURCE = "data"
    
    print("Processing inbox...")
    output = process_inbox(DATA_SOURCE)

    # Save to JSON
    with open("submission.json", "w") as f:
        json.dump(output, f, indent=2)

    # Self-evaluation trigger
    inbox = loader.Inbox(DATA_SOURCE)
    try:
        score = inbox.submit(output)
        print("Evaluation Scoreboard:", score)
    except Exception as err:
        print(f"Submission finished (Local server eval not triggered: {err})")