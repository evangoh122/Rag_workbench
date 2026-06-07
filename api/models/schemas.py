from pydantic import BaseModel
from typing import List, Optional, Dict

class ChatRequest(BaseModel):
    message: str
    history: Optional[List[Dict[str, str]]] = None

class ChatResponse(BaseModel):
    type: str
    answer: str
    sql: Optional[str] = None
    data: Optional[List[Dict]] = None

class HealthResponse(BaseModel):
    status: str
    provider: str
