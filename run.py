import uvicorn
import os
from loguru import logger

if __name__ == "__main__":
    logger.info("Starting RAG Workbench API on http://localhost:8000")
    logger.info("Swagger docs available at http://localhost:8000/docs")
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)
