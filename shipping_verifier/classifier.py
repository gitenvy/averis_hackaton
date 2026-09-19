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

1. "bl_comparison": The email asks to compare, verify, check, or audit a Shipping Instruction (SI) against a draft Bill of Lading (BL) for discrepancies or defects.
2. "si_request": The email requests issuing, drafting, submitting, or updating a Shipping Instruction (SI), or provides SI details/booking instructions.
3. "invoice_query": The email's CORE subject/intent is asking about billing, invoices, payment status, tax invoices, or freight charges.
4. "general": General operational inquiries, vessel schedules, tracking/ETA requests, container status, or routine logistics communications.
5. "spam": Marketing material, promotional emails, junk, or completely irrelevant topics.

Respond ONLY with a JSON object in this exact schema:
{
  "category": "bl_comparison" | "si_request" | "invoice_query" | "general" | "spam",
  "reasoning": "Brief 1-sentence rationale"
}"""


def classify_email(email: Dict[str, Any]) -> str:
    subject = str(email.get("subject") or "").strip()
    body = str(email.get("body") or "").strip()
    attachments = email.get("attachments") or []

    # Heuristic check for attachments to prevent misclassifying BL_COMPARISON
    att_str = str(attachments).lower()
    content_lower = f"{subject} {body}".lower()

    if any(k in att_str or k in content_lower for k in ["si_vs_bl", "bl_comparison", "draft bl", "check bl"]):
        return "BL_COMPARISON"

    if any(k in content_lower for k in ["casino", "crypto investment", "unsubscribed", "lottery"]):
        if not any(k in content_lower for k in ["shipping", "lading", "container", "booking"]):
            return "SPAM"

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

    if any(k in content_lower for k in ["shipping instruction", "submit si", "si details", "draft si"]):
        return "SI_REQUEST"
    elif "invoice" in subject.lower() or "billing" in subject.lower() or "payment" in subject.lower():
        return "INVOICE_QUERY"

    return "GENERAL"