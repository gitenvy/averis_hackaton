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

def clean_str(val: str) -> str:
    return re.sub(r'[^\w\s]', '', str(val)).strip().lower()

def is_field_matching(field: str, val_si: Any, val_bl: Any) -> bool:
    if val_si is None or val_bl is None:
        return val_si == val_bl

    # Numeric exact matches
    if field in ["container_count", "gross_weight_kg"]:
        try:
            return abs(float(val_si) - float(val_bl)) < 0.01
        except (ValueError, TypeError):
            return str(val_si) == str(val_bl)

    # Fuzzy string matching for textual fields (ports, names)
    s1, s2 = clean_str(val_si), clean_str(val_bl)
    if s1 == s2:
        return True
    
    # Token set ratio ignores word order differences ("Port of Loading: Singapore" vs "Singapore POL")
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