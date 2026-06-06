import uvicorn
import os

if __name__ == "__main__":
    print("Starting RAG Workbench API on http://localhost:8000")
    print("Swagger docs available at http://localhost:8000/docs")
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)
