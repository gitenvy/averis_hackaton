from typing import Dict, Any, Literal
from pydantic import BaseModel, Field
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

client = genai.Client()

class EmailClassification(BaseModel):
    category: Literal[
        "document_comparison_request",
        "new_si_request",
        "invoice_query",
        "general_message",
        "spam"
    ] = Field(description="The primary classification of the email.")

def classify_email(email: Dict[str, Any]) -> str:
    subject = email.get("subject", "")
    body = email.get("body", "")
    
    prompt = f"""
    Classify the following email into exactly one category:
    - document_comparison_request: Request to check, compare, or verify a Shipping Instruction (SI) against a Bill of Lading (BL).
    - new_si_request: Request to draft or prepare a brand new SI.
    - invoice_query: Billing, payment, or invoice questions.
    - general_message: Operational updates or general communications.
    - spam: Marketing, promotional, or unsolicited irrelevant emails.

    Subject: {subject}
    Body: {body}
    """
    
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=EmailClassification,
            ),
        )
        
        if response.text is None:
            return "general_message"

        parsed = EmailClassification.model_validate_json(response.text)
        return parsed.category
    except Exception:
        return "general_message"