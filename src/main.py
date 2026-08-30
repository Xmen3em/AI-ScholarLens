import logging
import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from opensearchpy.exceptions import OpenSearchException
from src.config import get_settings
from src.db.factory import make_database
from src.routers import papers, ping, search
from src.search.factory import make_search_client
from src.services.arxiv.factory import make_arxiv_client
from src.services.search import SearchService

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan for the API.
    """
    logger.info("Starting RAG API...")

    settings = get_settings()
    app.state.settings = settings

    database = make_database()
    app.state.database = database
    logger.info("Database connected")

    # Initialize API services (PDF parsing runs in the Airflow worker image)
    app.state.arxiv_client = make_arxiv_client()
    # Built here rather than per request: the OpenSearch client holds a connection
    # pool, and rebuilding it on every search would throw that pool away each time.
    app.state.search = SearchService(make_search_client())
    logger.info("Services initialized: arXiv API client, search")

    logger.info("API ready")
    yield

    # Cleanup
    database.teardown()
    logger.info("API shutdown complete")


app = FastAPI(
    title="arXiv Paper Curator API",
    description="Personal arXiv CS.AI paper curator with RAG capabilities",
    version=os.getenv("APP_VERSION", "0.1.0"),
    lifespan=lifespan,
)

@app.exception_handler(OpenSearchException)
async def search_backend_unavailable(request: Request, exc: Exception) -> JSONResponse:
    """The search backend being unreachable or refusing a query is a 503, not a 500.

    Registered once rather than wrapped around each search route: the mapping is a
    property of the dependency, not of any one endpoint. A missing index does not
    arrive here — the search service answers that with an empty result.
    """
    logger.error("Search backend failed for %s: %s", request.url.path, exc)
    return JSONResponse(status_code=503, content={"detail": "Search is unavailable"})


# Include routers
app.include_router(ping.router, prefix="/api/v1")
app.include_router(papers.router, prefix="/api/v1")
app.include_router(search.router, prefix="/api/v1")


if __name__ == "__main__":
    uvicorn.run(app, port=8000, host="0.0.0.0")
