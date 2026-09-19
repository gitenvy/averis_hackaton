import re
from typing import Dict, Any, Tuple
from rapidfuzz import fuzz
from dotenv import load_dotenv

load_dotenv()

TARGET_FIELDS = [
    "shipper", "consignee", "notify_party",
    "port_of_loading", "port_of_discharge",
    "container_count", "gross_weight_kg"
]

def clean_val(val: Any) -> Any:
    """Normalizes string inputs by stripping non-alphanumeric characters and extra spaces."""
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None
    # Remove punctuation and collapse multiple whitespaces/newlines into a single space
    s = re.sub(r'[^\w\s]', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip().lower()
    return s if s else None

def is_field_matching(field: str, val_si: Any, val_bl: Any) -> bool:
    # Normalize empty strings to None
    val_si = None if val_si == "" else val_si
    val_bl = None if val_bl == "" else val_bl

    # Both missing or one missing
    if val_si is None or val_bl is None:
        return val_si == val_bl

    # 1. Numeric Fields (container_count, gross_weight_kg)
    if field in ["container_count", "gross_weight_kg"]:
        try:
            # Clean string numbers containing commas (e.g. "12,500.00" -> 12500.0)
            num_si = float(str(val_si).replace(',', '').strip())
            num_bl = float(str(val_bl).replace(',', '').strip())
            return abs(num_si - num_bl) < 0.01
        except (ValueError, TypeError):
            return str(val_si).strip() == str(val_bl).strip()

    # 2. Textual Fields (shipper, consignee, notify_party, ports)
    s1 = clean_val(val_si)
    s2 = clean_val(val_bl)

    if s1 is None or s2 is None:
        return s1 == s2

    if s1 == s2:
        return True

    # Token set ratio handles word reordering and minor OCR variance
    return fuzz.token_set_ratio(s1, s2) >= 85.0

def compare_shipments(si: Dict[str, Any], bl: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    mismatches = {}
    has_mismatch = False

    for field in TARGET_FIELDS:
        val_si = si.get(field)
        val_bl = bl.get(field)

        if not is_field_matching(field, val_si, val_bl):
            has_mismatch = True
            mismatches[field] = {"si": val_si, "bl": val_bl}

    return has_mismatch, mismatches