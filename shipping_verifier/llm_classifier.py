import os
import json
from typing import Dict, Any
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

# Initialize OpenAI client pointed to OpenRouter
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),
)
MODEL_NAME = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct")

VALID_CATEGORIES = {"bl_comparison", "si_request", "invoice_query", "general", "spam"}

SYSTEM_PROMPT = """You are an expert shipping and logistics email classification engine.
Your job is to classify the primary intent of an email into EXACTLY ONE of the following 5 categories:

1. "bl_comparison": The email asks to compare, verify, check, or audit a Shipping Instruction (SI) against a draft Bill of Lading (BL) for discrepancies or defects. Requires BOTH documents or explicit instructions to compare/audit SI vs BL.
2. "si_request": The email requests issuing, drafting, submitting, or updating a Shipping Instruction (SI), or provides SI/booking details. It does NOT ask to compare an SI against a draft BL.
3. "invoice_query": The email's CORE subject/intent is asking about billing, invoices, payment status, tax invoices, or freight charges.
4. "general": General operational inquiries, vessel schedules, tracking/ETA requests, container status, or routine logistics communications.
5. "spam": Marketing material, promotional emails, junk, or completely irrelevant topics.

CRITICAL DISAMBIGUATION RULES:
- If the email provides, submits, or requests a Shipping Instruction (SI) WITHOUT asking to check/compare it against a draft BL, classify strictly as "si_request".
- Classify as "bl_comparison" ONLY if there is a draft BL involved AND an intent to compare or check for discrepancies between the SI and draft BL.

Respond ONLY with a JSON object in this exact schema:
{
  "category": "bl_comparison" | "si_request" | "invoice_query" | "general" | "spam",
  "reasoning": "Brief 1-sentence rationale"
}"""


def classify_email_llm(email: Dict[str, Any]) -> str:
    subject = str(email.get("subject") or "").strip()
    body = str(email.get("body") or "").strip()
    attachments = email.get("attachments") or []

    att_str = str(attachments).lower()
    content_lower = f"{subject} {body}".lower()
    full_text = f"{content_lower} {att_str}"

    # Fast SPAM filter
    if any(k in content_lower for k in ["casino", "crypto investment", "unsubscribed", "lottery"]):
        if not any(k in content_lower for k in ["shipping", "lading", "container", "booking"]):
            return "SPAM"

    # Precise Heuristic Pre-filters
    has_si = any(k in full_text for k in ["si", "shipping_instruction", "shipping instruction", "draft_si"])
    has_bl = any(k in full_text for k in ["bl", "bill_of_lading", "bill of lading", "draft_bl", "draft bl", "lading"])
    has_compare = any(k in full_text for k in ["compare", "discrepancy", "si vs bl", "bl vs si", "audit", "check bl", "si_vs_bl", "bl_comparison"])

    # Explicit BL_COMPARISON: Comparison keywords present OR both SI and BL attachments exist
    if has_compare or (has_si and has_bl and "draft" in full_text):
        return "BL_COMPARISON"

    # Explicit SI_REQUEST: Has SI details/attachment but NO draft BL and NO comparison request
    if has_si and not has_bl and not has_compare:
        return "SI_REQUEST"

    user_prompt = f"Subject: {subject}\nAttachments: {json.dumps(attachments)}\n\nEmail Body:\n{body[:2500]}"

    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.0,
        )

        raw_content = response.choices[0].message.content or "{}"
        result_json = json.loads(raw_content)
        category = str(result_json.get("category", "")).lower().strip()

        if category in VALID_CATEGORIES:
            return category.upper()

        for valid_cat in VALID_CATEGORIES:
            if valid_cat in category:
                return valid_cat.upper()

    except Exception as e:
        print(f"   [WARN] OpenRouter Classifier API error ({e}), applying fallback rules.")

    # Rule-based Fallbacks
    if has_compare or (has_si and has_bl):
        return "BL_COMPARISON"
    elif has_si or any(k in content_lower for k in ["shipping instruction", "submit si", "si details", "draft si"]):
        return "SI_REQUEST"
    elif "invoice" in subject.lower() or "billing" in subject.lower() or "payment" in subject.lower():
        return "INVOICE_QUERY"

    return "GENERAL"