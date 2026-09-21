"""Hybrid email classifier: attachments -> local ML model -> LLM (OpenRouter) -> keyword scorer.

Drop-in replacement: main.py still calls classify_email(email) and gets a category string.
The LLM is only called when the local model is unsure AND OPENROUTER_API_KEY is set.
"""
import os
from pathlib import Path
from typing import Any, Dict

import hackathonprototype as hp
import ml_pipeline as ml

MODEL_PATH = Path(os.getenv("EMAIL_MODEL_PATH", Path(__file__).with_name("model.joblib")))
_model = None
LAST_SOURCE = "none"          # which stage decided the last email (for logging/metrics)


def _load_model():
    global _model
    if _model is None and MODEL_PATH.exists():
        import joblib
        _model = joblib.load(MODEL_PATH)
    return _model


def classify_email(email: Dict[str, Any]) -> str:
    global LAST_SOURCE
    # 1. structural rule: named SI + BL attachments
    si, bl = hp.find_si_bl_paths([a for a in (email.get("attachments") or []) if isinstance(a, str)])
    if si and bl:
        LAST_SOURCE = "attachment_pair"
        return "BL_COMPARISON"

    # 2. local model
    model = _load_model()
    keyword_guess = hp.classify_email(email)["category"]
    if model is not None:
        p = model.predict_proba([email])[0]
        i = int(p.argmax())
        if p[i] >= ml.CONFIDENCE_THRESHOLD:
            LAST_SOURCE = "ml_model"
            return str(model.clf.classes_[i])

    # 3. LLM only for uncertain emails, and only if a key is configured
    if os.getenv("OPENROUTER_API_KEY"):
        try:
            from llm_classifier import classify_email_llm
            LAST_SOURCE = "llm"
            return classify_email_llm(email)
        except Exception as exc:
            print(f"   [WARN] LLM fallback failed ({exc}); using keyword scorer.")

    # 4. free fallback
    LAST_SOURCE = "keyword_fallback"
    return keyword_guess
