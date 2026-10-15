from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PaymentRequest(BaseModel):
    booking_id: int
    card_holder: str = Field(min_length=2, max_length=80)
    card_number: str = Field(pattern=r"^\d{13,19}$")
    expiry: str = Field(pattern=r"^(0[1-9]|1[0-2])/\d{2}$")  # MM/YY
    cvv: str = Field(pattern=r"^\d{3,4}$")

    @field_validator("card_number", mode="before")
    @classmethod
    def strip_spaces(cls, value):
        return value.replace(" ", "").replace("-", "") if isinstance(value, str) else value


class PaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    booking_id: int
    amount: float
    card_last4: str
    status: str
    transaction_ref: str
    created_at: datetime
