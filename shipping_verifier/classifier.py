import os
import json
from typing import Dict, Any
from dotenv import load_dotenv
from groq import Groq

load_dotenv()

# Initialize Groq client and dynamic model selection
client = Groq(api_key=os.getenv("GROQ_API_KEY"))
MODEL_NAME = os.getenv("GROQ_MODEL", "allam-2-7b")

VALID_CATEGORIES = {"bl_comparison", "si_request", "invoice_query", "general", "spam"}

SYSTEM_PROMPT = """You are an expert shipping and logistics email classification engine.
Your job is to classify the primary intent of an email into EXACTLY ONE of the following 5 categories:

1. "bl_comparison": The email asks to compare, verify, check, or audit a Shipping Instruction (SI) against a draft Bill of Lading (BL) for discrepancies or defects.
2. "si_request": The email requests issuing, drafting, submitting, or updating a Shipping Instruction (SI), or provides SI details/booking instructions.
3. "invoice_query": The email's CORE subject/intent is asking about billing, invoices, payment status, tax invoices, or freight charges.
   CRITICAL RULE: Ignore routine payment disclaimers, billing footnotes, account details in email signatures, or standard company disclaimers. Only classify as "invoice_query" if the sender is explicitly asking about an invoice or payment.
4. "general": General operational inquiries, vessel schedules, tracking/ETA requests, container status, or routine logistics communications.
5. "spam": Marketing material, promotional emails, junk, or completely irrelevant topics.

Respond ONLY with a JSON object in this exact schema:
{
  "category": "bl_comparison" | "si_request" | "invoice_query" | "general" | "spam",
  "reasoning": "Brief 1-sentence rationale"
}"""


def classify_email(email: Dict[str, Any]) -> str:
    """
    Classifies an email into one of 5 target categories:
    Returns uppercase category: BL_COMPARISON, SI_REQUEST, INVOICE_QUERY, GENERAL, SPAM
    """
    subject = str(email.get("subject") or "").strip()
    body = str(email.get("body") or "").strip()
    attachments = email.get("attachments") or []

    # Fast heuristic pre-filter for obvious SPAM
    content_lower = f"{subject} {body}".lower()
    if any(term in content_lower for term in ["casino", "crypto investment", "unsubscribed", "lottery"]):
        if not any(k in content_lower for k in ["shipping", "lading", "container", "booking"]):
            return "SPAM"

    body_snippet = body[:2500]

    user_prompt = f"""Subject: {subject}
Attachments: {json.dumps(attachments)}

Email Body:
{body_snippet}"""

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

        # Type-safe content parsing for Pylance
        raw_content = response.choices[0].message.content or "{}"
        result_json = json.loads(raw_content)
        category = str(result_json.get("category", "")).lower().strip()

        if category in VALID_CATEGORIES:
            return category.upper()

        for valid_cat in VALID_CATEGORIES:
            if valid_cat in category:
                return valid_cat.upper()

    except Exception as e:
        print(f"   [WARN] LLM Classifier API error ({e}), applying fallback rules.")

    # Rule-based Fallbacks in case of API timeout
    has_attachments = bool(attachments)
    
    if has_attachments and any(k in content_lower for k in ["compare", "discrepancy", "draft bl", "si vs bl", "check bl"]):
        return "BL_COMPARISON"
    elif any(k in content_lower for k in ["shipping instruction", "submit si", "si details", "draft si", "si request"]):
        return "SI_REQUEST"
    elif "invoice" in subject.lower() or "billing" in subject.lower() or "payment" in subject.lower():
        return "INVOICE_QUERY"

    return "GENERAL"