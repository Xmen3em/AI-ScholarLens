import asyncio
import logging
import sys
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Any, Optional, Tuple

sys.path.insert(0, "/opt/airflow")

from sqlalchemy import text
from src.db.factory import make_database
from src.repositories.paper import PaperRepository
from src.search.factory import make_search_client
from src.services.arxiv.factory import make_arxiv_client
from src.services.chunk_indexer import ChunkIndexer
from src.services.embeddings.factory import make_embedder
from src.services.metadata_fetcher import make_metadata_fetcher
from src.services.paper_indexer import PaperIndexer
from src.services.pdf_parser.factory import make_pdf_parser_service
from src.services.reindex import IndexRun

logger = logging.getLogger(__name__)

@lru_cache(maxsize=1)
def get_cached_services() -> Tuple[Any, Any, Any, Any]:
    """
    Get cached instances of the services used in the DAG.
    This function is decorated with lru_cache to ensure that the services are only created once per DAG run.
    """
    logger.info("Creating cached service instances...")
    database = make_database()
    arxiv_client = make_arxiv_client()
    pdf_parser = make_pdf_parser_service()
    metadata_fetcher = make_metadata_fetcher(arxiv_client, pdf_parser)

    logger.info("Cached service instances created successfully.")
    return arxiv_client,  pdf_parser, database, metadata_fetcher

async def run_paper_ingestion_pipeline(
    target_date: str,
    max_results: Optional[int] = None,
    process_pdfs: bool = True,
) -> dict:
    """
    Run the paper ingestion pipeline.
    This function orchestrates the entire process of fetching, parsing, and storing papers from arXiv.
    """
    _arxiv_client, _pdf_parser, database, metadata_fetcher = get_cached_services()
    
    with database.get_session() as session:
        # Fetch papers from arXiv
        return await metadata_fetcher.fetch_and_process_papers(
            max_results=max_results,
            from_date=target_date,
            to_date=target_date,
            process_pdfs=process_pdfs,
            store_to_db=True,
            db_session=session,
        )
        
def setup_environment():
    """
    Setup the environment for the DAG.
    This function can be used to set up any necessary environment variables or configurations.
    """
    logger.info("Setting up environment for arxiv ingestion...")
    # Example: Set up environment variables or configurations here
    # os.environ["SOME_ENV_VAR"] = "value"

    try:
        # Perform any necessary setup here
        arxiv_client, _pdf_parser, database, _metadata_fetcher = get_cached_services()
        
        with database.get_session() as session:
            # Test database connection
            session.execute(text("SELECT 1"))
            logger.info("Database connection successful.")
            
        logger.info(f"arxiv client ready : {arxiv_client.base_url}")
        logger.info("Environment setup completed successfully.")
        
        return {"status": "success", "message": "Environment setup completed successfully."}
    
    except Exception as e:
        error_msg = f"Error during environment setup: {str(e)}"
        logger.error(error_msg)
        raise Exception(error_msg)
    
    
def fetch_daily_papers(**context):
    """
    Fetch daily papers from arXiv and store them in the database.
    This function is designed to be used as an Airflow task.
    """
    logger.info("Starting daily paper ingestion task...")
    
    try:
        execution_date = context['ds']
        execution_dt = datetime.strptime(execution_date, "%Y-%m-%d")
        target_dt = execution_dt - timedelta(days=1)
        # arXiv's submittedDate filter needs YYYYMMDD; a dashed date silently matches nothing.
        target_date = target_dt.strftime("%Y%m%d")
        logger.info(f"Fetching papers for date: {target_date}")
        

        # max_results is left unset so ARXIV__MAX_RESULTS drives the batch size.
        results = asyncio.run(run_paper_ingestion_pipeline(
            target_date=target_date,
            process_pdfs=True
            )
                            )
        if results.get("errors"):
            logger.warning(
                f"Paper ingestion completed with {len(results['errors'])} errors "
                f"({results.get('pdfs_parsed', 0)} parsed, {results.get('pdfs_skipped', 0)} skipped). Results: {results}"
            )
        else:
            logger.info(f"Paper ingestion completed successfully. Results: {results}")
        
        context['task_instance'].xcom_push(key='fetch_results', value=results)
        
        return results
    
    except Exception as e:
        error_msg = f"Error during daily paper ingestion: {str(e)}"
        logger.error(error_msg)
        raise Exception(error_msg)
    
    
def process_failed_pdfs(**context):
    """
    Process failed PDFs from previous ingestion attempts.
    This function is designed to be used as an Airflow task.
    """
    logger.info("Starting failed PDF processing task...")
    
    try:
        fetch_results = context['task_instance'].xcom_pull(key='fetch_results', task_ids='fetch_daily_papers')
    
        if not fetch_results or not fetch_results.get('errors'):
            logger.info("No failed PDFs to process.")
            return {"status": "success", "message": "No failed PDFs to process."}
        
        logger.info(f"Found {len(fetch_results['errors'])} failed PDFs to process.")
        
        for error in fetch_results['errors']:
            logger.info(f"Error to investigate: {error}")
        
        return {
            "status": "analyzed",
            "errors_logged": len(fetch_results["errors"]),
            "message": "Errors logged for investigation",
        }           
    except Exception as e:
        error_msg = f"Error during failed PDF processing: {str(e)}"
        logger.error(error_msg)
        raise Exception(error_msg)
    
    
def index_to_opensearch(**context):
    """Rewrite both OpenSearch indices from what is stored in PostgreSQL.

    Both indices in one task because they describe the same corpus and must not drift
    apart: a paper searchable in `arxiv-papers` whose passages are missing from
    `paper-chunks` is worse than neither being updated.

    Indexes the whole corpus rather than just this run's papers. The pass is
    idempotent — document ids are derived from the paper — and that is what lets it
    heal a run that failed halfway and pick up papers stored before indexing existed.
    """
    logger.info("Indexing papers and chunks into OpenSearch...")

    try:
        _arxiv_client, _pdf_parser, database, _metadata_fetcher = get_cached_services()
        client = make_search_client()

        with database.get_session() as session:
            repository = PaperRepository(session)
            papers = PaperIndexer(client, repository).index_corpus()
            chunks = ChunkIndexer(client, repository, make_embedder()).index_corpus()

        errors = papers.errors + chunks.errors
        results = {
            "status": "failed" if errors else "success",
            "papers": _index_summary(papers),
            "chunks": _index_summary(chunks),
            "errors": errors,
        }

        # Loud, but not fatal: whatever did index is still searchable, and the next
        # run rewrites everything anyway.
        for error in errors:
            logger.error("Indexing error: %s", error)

        logger.info(
            "Indexed %d paper documents and %d chunks",
            papers.documents_indexed,
            chunks.documents_indexed,
        )
        return results

    except Exception as e:
        error_msg = f"Error during OpenSearch indexing: {str(e)}"
        logger.error(error_msg)
        raise Exception(error_msg)


def _index_summary(run: IndexRun) -> dict:
    """One index pass, flattened for XCom."""
    return {
        "papers_seen": run.papers_seen,
        "papers_indexed": run.papers_indexed,
        "papers_without_documents": run.papers_without_documents,
        "documents_indexed": run.documents_indexed,
        "stale_documents_deleted": run.stale_documents_deleted,
        "embeddings_computed": run.embeddings_computed,
        "embeddings_reused": run.embeddings_reused,
    }


def generate_daily_report(**context):
    """
    Generate a daily report of the ingestion process.
    This function is designed to be used as an Airflow task.
    """
    logger.info("Starting daily report generation task...")
    
    try:
        fetch_results = context['task_instance'].xcom_pull(key='fetch_results', task_ids='fetch_daily_papers')
        
        failed_pdf_results = context['task_instance'].xcom_pull(task_ids='process_failed_pdfs')
        
        index_results = context['task_instance'].xcom_pull(task_ids='index_to_opensearch')
        
        report = {
            'date': context['ds'],
            "execution_time": datetime.now().isoformat(),
            "papers": {
                "fetched": fetch_results.get('papers_fetched', 0) if fetch_results else 0,
                "pdfs_downloaded": fetch_results.get('pdfs_downloaded', 0) if fetch_results else 0,
                "pdfs_parsed": fetch_results.get('pdfs_parsed', 0) if fetch_results else 0,
                "pdfs_skipped": fetch_results.get('pdfs_skipped', 0) if fetch_results else 0,
                "filtered_non_ai": fetch_results.get('papers_filtered_non_ai', 0) if fetch_results else 0,
                "stored": fetch_results.get('papers_stored', 0) if fetch_results else 0,
            },
            "processing": {
                "processing_time_seconds": fetch_results.get('processing_time', 0) if fetch_results else 0,
                "errors": len(fetch_results.get('errors', [])) if fetch_results else 0,
                "failed_pdf_retries": failed_pdf_results.get('errors_logged', 0) if failed_pdf_results else 0,
            },
            "opensearch": {
                "papers_indexed": index_results['papers']['documents_indexed'] if index_results else 0,
                "chunks_indexed": index_results['chunks']['documents_indexed'] if index_results else 0,
                "papers_without_chunks": index_results['chunks']['papers_without_documents'] if index_results else 0,
                "embeddings_computed": index_results['chunks']['embeddings_computed'] if index_results else 0,
                "embeddings_reused": index_results['chunks']['embeddings_reused'] if index_results else 0,
                "status": index_results.get('status', 'unknown') if index_results else 'unknown',
            }
        }   
        
        logger.info("=== DAILY ARXIV PROCESSING REPORT ===")
        logger.info(f"Date: {report['date']}")
        logger.info(f"Papers fetched: {report['papers']['fetched']}")
        logger.info(f"Filtered as non-AI: {report['papers']['filtered_non_ai']}")
        logger.info(f"PDFs downloaded: {report['papers']['pdfs_downloaded']}")
        logger.info(f"PDFs parsed: {report['papers']['pdfs_parsed']}")
        logger.info(f"PDFs skipped (size/page limits): {report['papers']['pdfs_skipped']}")
        logger.info(f"Papers stored: {report['papers']['stored']}")
        logger.info(f"Processing time: {report['processing']['processing_time_seconds']:.1f}s")
        logger.info(f"Errors encountered: {report['processing']['errors']}")
        logger.info(f"Papers searchable: {report['opensearch']['papers_indexed']}")
        logger.info(f"Chunks indexed: {report['opensearch']['chunks_indexed']}")
        logger.info(f"Papers with no chunks (unparsed): {report['opensearch']['papers_without_chunks']}")
        logger.info(f"Embeddings computed: {report['opensearch']['embeddings_computed']} (reused {report['opensearch']['embeddings_reused']})")
        logger.info("=== END REPORT ===")

        # Without this the report exists only in the task log, so nothing downstream
        # can read it and the run's numbers vanish once logs rotate.
        return report

    except Exception as e:
        error_msg = f"Error during daily report generation: {str(e)}"
        logger.error(error_msg)
        raise Exception(error_msg)
