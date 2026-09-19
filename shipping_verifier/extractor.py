import json
from typing import Optional
from pydantic import BaseModel, Field
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

client = genai.Client()  # Automatically uses GEMINI_API_KEY from .env

class ShipmentDetails(BaseModel):
    shipper: Optional[str] = Field(None, description="Name and address of shipper/exporter")
    consignee: Optional[str] = Field(None, description="Name and address of consignee")
    notify_party: Optional[str] = Field(None, description="Notify party details")
    port_of_loading: Optional[str] = Field(None, description="Port of loading/POL")
    port_of_discharge: Optional[str] = Field(None, description="Port of discharge/POD")
    container_count: Optional[int] = Field(None, description="Total number of containers")
    gross_weight_kg: Optional[float] = Field(None, description="Gross weight in kilograms (numeric only)")

def extract_shipment_details(document_text: str) -> ShipmentDetails:
    prompt = f"""
    Extract shipment details from the following document.
    Normalize gross weight into kilograms (e.g. convert metric tons to kg if needed).
    If a field is missing, unreadable, or not mentioned, set it to null.
    
    Document Text:
    {document_text}
    """
    
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ShipmentDetails,
        ),
    )
    
    # Type guard for Pylance: Ensure response.text is not None/empty
    if not response.text:
        raise ValueError("Failed to extract structured shipment details: Empty response from Gemini API.")

    return ShipmentDetails.model_validate_json(response.text)