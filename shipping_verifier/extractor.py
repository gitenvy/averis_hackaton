import os
import json
from typing import Dict, Any, Optional, Union
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),
)
MODEL_NAME = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct")

EXTRACTION_SYSTEM_PROMPT = """You are an expert shipping document entity extraction engine.
Your task is to parse raw document text or email contents and extract standard Bill of Lading (BL) / Shipping Instruction (SI) fields.

Extract the following fields accurately:
- shipper: Full company name/address of the shipper/exporter.
- consignee: Full company name/address of the consignee/receiver.
- notify_party: Party to be notified upon arrival.
- vessel: Name of the cargo vessel.
- voyage: Voyage or flight number.
- port_of_loading: Port where goods are loaded (POL).
- port_of_discharge: Port where goods are delivered (POD).
- container_number: Container ID(s) (e.g., MSCU1234567).
- seal_number: Container seal ID.
- cargo_description: Description of goods/cargo.
- gross_weight: Total weight string including unit (e.g., "12500 KGS").
- measurement: Volume/CBM string (e.g., "32.5 CBM").

Rules:
1. Normalize missing or unknown fields to null.
2. Maintain clean, standardized key names.
3. Return ONLY a valid JSON object.

JSON Schema Output:
{
  "shipper": string | null,
  "consignee": string | null,
  "notify_party": string | null,
  "vessel": string | null,
  "voyage": string | null,
  "port_of_loading": string | null,
  "port_of_discharge": string | null,
  "container_number": string | null,
  "seal_number": string | null,
  "cargo_description": string | null,
  "gross_weight": string | null,
  "measurement": string | null
}"""


def extract_document_fields(document_text: str, doc_type: str = "DOCUMENT") -> Dict[str, Optional[str]]:
    if not document_text or not document_text.strip():
        return {}

    user_prompt = f"Document Type: {doc_type}\n\nDocument Text Content:\n{document_text[:4000]}"

    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.0,
        )

        raw_content = response.choices[0].message.content or "{}"
        extracted_data = json.loads(raw_content)

        cleaned_fields = {}
        for key, val in extracted_data.items():
            if isinstance(val, str):
                val_clean = val.strip()
                cleaned_fields[key] = val_clean if val_clean and val_clean.lower() != "null" else None
            else:
                cleaned_fields[key] = val

        return cleaned_fields

    except Exception as e:
        print(f"   [WARN] OpenRouter Extractor API error ({e}). Returning empty extraction.")
        return {}


def extract_shipment_details(
    input_data: Union[str, Dict[str, Any]], 
    doc_type: str = "DOCUMENT"
) -> Dict[str, Optional[str]]:
    if isinstance(input_data, dict):
        subject = str(input_data.get("subject") or "").strip()
        body = str(input_data.get("body") or "").strip()
        combined_text = f"Subject: {subject}\n\nBody:\n{body}"
        return extract_document_fields(combined_text, doc_type=doc_type)

    return extract_document_fields(str(input_data or ""), doc_type=doc_type)