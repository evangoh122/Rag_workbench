# Reviewed by Mimo: LGTM
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from langchain_openai import ChatOpenAI
from api.config import Config

class FinancialTriple(BaseModel):
    subject: str = Field(description="The subject entity of the financial relationship (e.g., Company, Segment, Product).")
    predicate: str = Field(description="The action, relationship, or connecting property (e.g., owns, increased by, exposed to).")
    object: str = Field(description="The object entity, metric, or concept (e.g., $10B, Market Risk, Subsidiary XYZ).")

class TriplesOutput(BaseModel):
    triples: List[FinancialTriple] = Field(description="List of extracted financial triples.")

SYSTEM_PROMPT = """You are an expert financial analyst. Your task is to extract relationships from the following SEC 10-K text.
Represent these relationships as a list of Subject-Predicate-Object triples.
Focus on key financial metrics, business segments, risks, and strategic initiatives.

{format_instructions}"""

def extract_triples(text: str, model_cfg: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """
    Extracts financial relationships as JSON triples (Subject, Predicate, Object) 
    from a string of raw SEC 10-K text.
    """
    if model_cfg is None:
        model_cfg = Config.get_provider_config()
        
    llm = ChatOpenAI(
        model=model_cfg.get("model", "gpt-4o"),
        api_key=model_cfg.get("api_key") or "local",
        base_url=model_cfg.get("base_url")
    )

    parser = JsonOutputParser(pydantic_object=TriplesOutput)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        ("user", "{text}")
    ])
    
    chain = prompt | llm | parser
    
    result = chain.invoke({
        "text": text,
        "format_instructions": parser.get_format_instructions()
    })
    
    # Return as list of dicts to match the required return type signature
    if isinstance(result, dict) and "triples" in result:
        return result["triples"]
    
    return result if isinstance(result, list) else []
