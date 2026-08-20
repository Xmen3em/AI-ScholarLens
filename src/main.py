import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from src.config import get_settings
from src.db.factory import make_database
from src.routers import ask, papers, ping

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting RAG API...")
    
    settings = get_settings()
    app.state.settings = settings
    
    database = make_database()
    app.state.database = database
    logger.info("Database connection established.")
    
    app.state.pdf_parser_service = None  # Placeholder for PDF parser service initialization
    app.state.opensearch_service = None  # Placeholder for OpenSearch service initialization
    app.state.llm_service = None  # Placeholder for LLM service initialization
    
    logger.info("RAG API started successfully.")
    yield
    
    database.treadown()
    logger.info("Database connection closed.")
    
    
app = FastAPI(
    lifespan=lifespan,
    title="Production-Grade AI Research Discovery & RAG Platform",
    description="Automated platform for ingesting, indexing, retrieving, and querying AI-focused arXiv research papers using FastAPI, PostgreSQL, OpenSearch hybrid search, Airflow, Ollama, and RAG",
    version=os.getenv("APP_VERSION", "0.1.0"),
    root_path="/api/v1"
    )

app.include_router(ping.router)
app.include_router(papers.router)
app.include_router(ask.router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, port=8000, host="0.0.0.0")