# app/models/user.py
from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime, date

class UserProfile(BaseModel):
    id: str
    email: EmailStr
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    birthday: Optional[date] = None
    gender: Optional[str] = None
    credits: int
    created_at: datetime
    updated_at: datetime

class UserCreditsUpdate(BaseModel):
    credits: int