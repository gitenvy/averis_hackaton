import time
import os
from typing import Dict, Any, Literal
from pydantic import BaseModel, Field
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=os.getenv("GROQ_API_KEY"),
)

class EmailClassification(BaseModel):
    category: Literal[
        "bl_comparison",
        "si_request",
        "invoice_query",
        "general",
        "spam"
    ] = Field(description="The primary classification of the email.")

def classify_email(email: Dict[str, Any]) -> str:
    subject = str(email.get("subject") or email.get("subject_line") or "").lower()
    body = str(email.get("body") or email.get("text") or email.get("content") or "").lower()
    content = f"{subject} {body}"
    attachments = email.get("attachments", {})
    has_attachments = bool(attachments)

    # 1. Local Keyword Pre-Classifier (Bypasses API call entirely)
    if any(k in content for k in ["casino", "lottery", "unsubscribed", "buy now", "crypto"]):
        return "spam"
    if any(k in content for k in ["invoice", "billing", "payment", "receipt", "remittance"]):
        return "invoice_query"
    if any(k in content for k in ["new si", "create si", "prepare si", "shipping instruction request"]):
        return "si_request"
    if has_attachments and any(k in content for k in ["compare", "draft bl", "check bl", "si vs bl", "verify", "discrepancy", "confirm", "confirm docs", "attached are the si", "bl for"]):
        return "bl_comparison"

    # 2. Groq API Fallback using allam-2-7b
    prompt = f"""
    Classify the following email into exactly one category.
    Return ONLY a JSON object with a single key "category":
    - "bl_comparison": Request to check, compare, or verify a Shipping Instruction (SI) against a Bill of Lading (BL).
    - "si_request": Request to draft or prepare a brand new SI.
    - "invoice_query": Billing, payment, or invoice questions.
    - "general": Operational updates or general communications.
    - "spam": Marketing, promotional, or unsolicited irrelevant emails.

    Subject: {subject}
    Body: {body}
    Has attachments: {has_attachments}
    """

    max_retries = 5
    wait_time = 2

    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model="allam-2-7b",
                messages=[
                    {"role": "system", "content": "You are a JSON-only classification assistant. Always output valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.0,
            )
            
            raw_text = response.choices[0].message.content
            if raw_text:
                parsed = EmailClassification.model_validate_json(raw_text)
                return parsed.category
            return "general"

        except Exception as e:
            err_msg = str(e)
            if any(code in err_msg for code in ["429", "500", "503", "rate_limit_exceeded"]):
                print(f"  [WARN] Groq Classifier API transient error ({type(e).__name__}): {e}. Retrying in {wait_time}s... (Attempt {attempt + 1}/{max_retries})")
                time.sleep(wait_time)
                wait_time += 3
            else:
                print(f"  [WARN] Classification error: {e}")
                return "general"

    return "general"