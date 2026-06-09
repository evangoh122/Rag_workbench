from pydantic import BaseModel, Field
from typing import List, Optional, Dict


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    ticker: Optional[str] = Field(default="NVDA", max_length=10)
    history: Optional[List[Dict[str, str]]] = Field(default=None, max_length=50)
