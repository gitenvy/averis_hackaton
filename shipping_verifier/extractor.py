import time
import os
import re
from typing import Optional, Any
from pydantic import BaseModel, Field, field_validator
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=os.getenv("GROQ_API_KEY"),
)

class ShipmentDetails(BaseModel):
    shipper: Optional[str] = Field(None, description="Name and address of shipper/exporter")
    consignee: Optional[str] = Field(None, description="Name and address of consignee")
    notify_party: Optional[str] = Field(None, description="Notify party details")
    port_of_loading: Optional[str] = Field(None, description="Port of loading/POL")
    port_of_discharge: Optional[str] = Field(None, description="Port of discharge/POD")
    container_count: Optional[int] = Field(None, description="Total number of containers")
    gross_weight_kg: Optional[float] = Field(None, description="Gross weight in kilograms (numeric only)")

    @field_validator("shipper", "consignee", "notify_party", "port_of_loading", "port_of_discharge", mode="before")
    @classmethod
    def flatten_to_string(cls, v: Any) -> Optional[str]:
        if isinstance(v, dict):
            parts = [str(val).strip() for val in v.values() if val is not None and str(val).strip()]
            return " ".join(parts) if parts else None
        if isinstance(v, list):
            parts = [str(val).strip() for val in v if val is not None and str(val).strip()]
            return " ".join(parts) if parts else None
        return str(v) if v is not None else None

    @field_validator("container_count", mode="before")
    @classmethod
    def parse_container_count(cls, v: Any) -> Optional[int]:
        if v is None or v == "":
            return None
        if isinstance(v, int):
            return v
        # Extract the first integer count from strings like "6 x 40'HC" or "1 x 20FT"
        match = re.search(r'\d+', str(v))
        if match:
            return int(match.group())
        return None

    @field_validator("gross_weight_kg", mode="before")
    @classmethod
    def parse_gross_weight(cls, v: Any) -> Optional[float]:
        if v is None or v == "":
            return None
        if isinstance(v, (int, float)):
            return float(v)
        
        s = str(v).upper().replace(",", "").strip()
        is_mt = "MT" in s or "TON" in s
        
        match = re.search(r'\d+(?:\.\d+)?', s)
        if match:
            val = float(match.group())
            # Convert Metric Tons to KG if indicated
            if is_mt and val < 1000:
                val *= 1000.0
            return val
        return None

def extract_shipment_details(document_text: str) -> ShipmentDetails:
    prompt = f"""
    Extract shipment details from the following document.
    Normalize gross weight into kilograms (e.g. convert metric tons to kg if needed).
    IMPORTANT: 
    - container_count MUST be a single integer (e.g., 1, 6).
    - All text fields MUST be flat strings, NOT nested objects or dictionaries.
    If a field is missing, unreadable, or not mentioned, set it to null.

    Document Text:
    {document_text}
    """

    max_retries = 5
    wait_time = 2
    last_exception: Optional[Exception] = None

    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model="allam-2-7b",
                messages=[
                    {"role": "system", "content": "You are a JSON-only extraction bot. Return strictly valid JSON adhering to the provided schema."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.0,
            )
            
            raw_text = response.choices[0].message.content
            if not raw_text:
                raise ValueError("Empty response from Groq API.")

            return ShipmentDetails.model_validate_json(raw_text)

        except Exception as e:
            last_exception = e
            err_msg = str(e)
            if any(code in err_msg for code in ["429", "500", "503", "rate_limit_exceeded"]):
                print(f"  [WARN] Groq Extractor API transient error ({type(e).__name__}): {e}. Retrying in {wait_time}s... (Attempt {attempt + 1}/{max_retries})")
                time.sleep(wait_time)
                wait_time += 3
            else:
                print(f"  [ERROR] Extractor hit exception: {e}")
                raise e

    if last_exception:
        raise last_exception
    raise RuntimeError("Failed to extract details after maximum retries.")