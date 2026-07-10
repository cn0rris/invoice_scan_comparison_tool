from typing import Optional

from pydantic import BaseModel, Field


class LineItem(BaseModel):
    description: str = Field(description="Description of the billed work or item")
    timekeeper: Optional[str] = Field(
        None,
        description=(
            "Name or initials of the person who performed this line item's work — "
            "may be labeled 'Timekeeper', 'Billed by', 'Attorney', 'Initials', etc."
        ),
    )
    hours: Optional[float] = Field(None, description="Hours billed, if time-based")
    rate: Optional[float] = Field(None, description="Hourly or unit rate")
    amount: Optional[float] = Field(None, description="Line item total amount")


class InvoiceExtraction(BaseModel):
    invoice_number: Optional[str] = Field(None, description="Invoice number/ID as printed")
    invoice_date: Optional[str] = Field(None, description="Invoice date, normalized to YYYY-MM-DD")
    vendor_name: Optional[str] = Field(None, description="Law firm / vendor issuing the invoice")
    client_name: Optional[str] = Field(None, description="Client being billed")
    matter_number: Optional[str] = Field(None, description="Client matter / engagement number, if present")
    line_items: list[LineItem] = Field(default_factory=list)
    subtotal: Optional[float] = Field(None, description="Sum of line items before tax")
    tax: Optional[float] = Field(None, description="Tax amount, 0 if none")
    total: Optional[float] = Field(None, description="Grand total due")
    currency: Optional[str] = Field("USD", description="ISO currency code")


def generate_default_prompt() -> str:
    lines = [
        "You are extracting structured data from a legal invoice (a PDF or image).",
        "Read the document carefully and return ONLY a JSON object with exactly these fields:",
        "",
    ]
    for name, field in InvoiceExtraction.model_fields.items():
        if name == "line_items":
            lines.append(
                '- line_items: array of objects, each with "description" (string), '
                '"timekeeper" (string or null — the person who performed this work; '
                'look for labels like "Timekeeper", "Billed by", "Attorney", or "Initials"), '
                '"hours" (number or null), "rate" (number or null), "amount" (number or null)'
            )
            continue
        desc = field.description or ""
        lines.append(f"- {name}: {desc}")
    lines += [
        "",
        "Rules:",
        "- If a field is not present on the invoice, use null (or an empty list for line_items).",
        "- Normalize invoice_date to YYYY-MM-DD regardless of the format printed on the invoice.",
        "- Do not invent values that are not supported by the document.",
        "- Return only the JSON object, with no surrounding prose or markdown formatting.",
    ]
    return "\n".join(lines)
