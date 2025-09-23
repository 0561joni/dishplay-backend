# app/models/menu.py
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class MenuItem(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    price: Optional[float] = None
    images: List[str] = []

class MenuResponse(BaseModel):
    success: bool
    message: str
    menu_id: str
    title: str
    items: List[MenuItem]
    credits_remaining: Optional[int] = None

class MenuListItem(BaseModel):
    id: str
    status: str
    processed_at: datetime
    item_count: int

class UserMenusResponse(BaseModel):
    menus: List[MenuListItem]
