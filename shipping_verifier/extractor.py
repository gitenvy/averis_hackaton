import json
from typing import Optional
from pydantic import BaseModel, Field
from openai import OpenAI

client = OpenAI()  # Assumes OPENAI_API_KEY environment variable

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
    
    Document Text:
    {document_text}
    """
    
    response = client.beta.chat.completions.parse(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        response_format=ShipmentDetails,
    )
    return response.choices[0].message.parsed