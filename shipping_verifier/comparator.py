import re
from typing import Dict, Any, Tuple, Optional

TARGET_FIELDS = [
    "shipper",
    "consignee",
    "notify_party",
    "port_of_loading",
    "port_of_discharge",
    "container_count",
    "gross_weight_kg"
]


def normalize_text(text: Any) -> str:
    """Strips punctuation, extra whitespace, and converts to lowercase."""
    if text is None:
        return ""
    s = str(text).lower()
    s = re.sub(r"[^\w\s]", " ", s)
    return " ".join(s.split())


def normalize_weight(weight_val: Any) -> Optional[float]:
    """Converts weight representations (e.g. '138 MT', '138,000 KGS', '138000 kg') to float KGs."""
    if weight_val is None:
        return None
    
    clean_str = str(weight_val).upper().replace(",", "").strip()
    match = re.search(r"([\d\.]+)\s*(MT|M/T|METRIC TON|KGS|KG)?", clean_str)
    if not match:
        return None
        
    try:
        val = float(match.group(1))
    except ValueError:
        return None
        
    unit = match.group(2) or "KG"
    
    if any(u in unit for u in ["MT", "M/T", "TON"]):
        return val * 1000.0
    return val


def normalize_container_count(count_val: Any) -> Optional[int]:
    """Extracts integer container count from string or numeric representations."""
    if count_val is None:
        return None
    clean_str = str(count_val).replace(",", "").strip()
    match = re.search(r"\d+", clean_str)
    if match:
        try:
            return int(match.group(0))
        except ValueError:
            return None
    return None


def compare_field(field: str, val1: Any, val2: Any) -> bool:
    """
    Returns True if fields match (no mismatch), False if they differ.
    Null/None values are skipped here as missing values are handled via review_reason.
    """
    if val1 is None or val2 is None:
        return True
        
    # 1. Weight comparison with unit normalization
    if field == "gross_weight_kg":
        w1 = normalize_weight(val1)
        w2 = normalize_weight(val2)
        if w1 is not None and w2 is not None:
            return abs(w1 - w2) < 1.0  # Allow 1 kg rounding tolerance
        return str(val1).strip().lower() == str(val2).strip().lower()

    # 2. Container count comparison
    if field == "container_count":
        c1 = normalize_container_count(val1)
        c2 = normalize_container_count(val2)
        if c1 is not None and c2 is not None:
            return c1 == c2
        return str(val1).strip().lower() == str(val2).strip().lower()

    # 3. General text comparison (Shipper, Consignee, Ports, Notify Party)
    t1 = normalize_text(val1)
    t2 = normalize_text(val2)
    
    if not t1 or not t2:
        return True
        
    if t1 == t2:
        return True
        
    # Token set equality (order-insensitive matching)
    tokens1 = set(t1.split())
    tokens2 = set(t2.split())
    
    return tokens1 == tokens2


def compare_shipments(si_dict: Dict[str, Any], bl_dict: Dict[str, Any]) -> Tuple[bool, Dict[str, Tuple[Any, Any]]]:
    """
    Compares extracted SI details against BL details for TARGET_FIELDS.
    Returns (has_mismatch, mismatches_dict).
    """
    mismatches = {}
    
    for field in TARGET_FIELDS:
        si_val = si_dict.get(field)
        bl_val = bl_dict.get(field)
        
        if not compare_field(field, si_val, bl_val):
            mismatches[field] = (si_val, bl_val)
            
    has_mismatch = len(mismatches) > 0
    return has_mismatch, mismatches