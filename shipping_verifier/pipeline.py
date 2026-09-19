from reader import read_attachment
from extractor import extract_shipment_details
from comparator import compare_shipments, TARGET_FIELDS

def process_comparison_case(si_path: str, bl_path: str) -> dict:
    result = {
        "has_mismatch": False,
        "mismatches": {},
        "needs_human_review": False,
        "review_reason": None
    }

    # Step 1: Read Files safely
    try:
        si_text = read_attachment(si_path)
        bl_text = read_attachment(bl_path)
    except Exception as e:
        result["needs_human_review"] = True
        result["review_reason"] = f"File read error: {str(e)}"
        return result

    # Step 2: Extract structured fields
    try:
        si_data = extract_shipment_details(si_text).model_dump()
        bl_data = extract_shipment_details(bl_text).model_dump()
    except Exception as e:
        result["needs_human_review"] = True
        result["review_reason"] = f"Extraction failure: {str(e)}"
        return result

    # Step 3: Check for incomplete/missing essential fields
    missing_fields = [f for f in TARGET_FIELDS if si_data.get(f) is None or bl_data.get(f) is None]
    if missing_fields:
        result["needs_human_review"] = True
        result["review_reason"] = f"Uncertain values or missing fields: {', '.join(missing_fields)}"

    # Step 4: Compare
    has_mismatch, mismatches = compare_shipments(si_data, bl_data)
    result["has_mismatch"] = has_mismatch
    result["mismatches"] = mismatches

    return result