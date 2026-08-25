import asyncio
import logging
import sys
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Any, Tuple

sys.path.insert(0, "/opt/airflow")

from sqlalchemy import text
from src.db.factory import make_database
from src.services.arxiv.factory import make_arxiv_client
from src.services.metadata_fetcher import make_metadata_fetcher
from src.services.pdf_parser.factory import make_pdf_parser_service

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
    max_results: int = 5,
    process_pdfs: bool = True,
) -> dict:
    """
    Run the paper ingestion pipeline.
    This function orchestrates the entire process of fetching, parsing, and storing papers from arXiv.
    """
    _arxiv_client, _pdf_parser, database, metadata_fetcher = get_cached_services()
    
    with database.get_session() as session:
        # Fetch papers from arXiv
        return await metadata_fetcher.fetch_and_store_papers(
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
        target_date = target_dt.strftime("%Y-%m-%d")
        logger.info(f"Fetching papers for date: {target_date}")
        

        results = asyncio.run(run_paper_ingestion_pipeline(
            target_date=target_date,
            max_results=10,
            process_pdfs=True
            )
                            )
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
    
    
def create_opensearch_placeholders(**context):
    """
    Create OpenSearch placeholders for the ingested papers.
    This function is designed to be used as an Airflow task.
    """
    logger.info("Starting OpenSearch placeholder creation task...")
    
    try:
        fetch_results = context['task_instance'].xcom_pull(key='fetch_results', task_ids='fetch_daily_papers')
        
        if not fetch_results:
            logger.info("No papers found to create OpenSearch placeholders.")
            return {"status": "success", "message": "No papers found to create OpenSearch placeholders."}
        
        papers_stored = fetch_results.get('papers_stored', 0)
        logger.info(f"Number of papers stored in the database: {papers_stored}")
        
        placeholder_results = {
            "status": "placeholder",
            "papers_ready_for_indexing": papers_stored,
            "message": f"OpenSearch placeholders created for {papers_stored} papers."
        }
        
        logger.info(f"OpenSearch placeholder creation completed successfully. Results: {placeholder_results}")        
        return placeholder_results
    
    except Exception as e:
        error_msg = f"Error during OpenSearch placeholder creation: {str(e)}"
        logger.error(error_msg)
        raise Exception(error_msg)
    

def generate_daily_report(**context):
    """
    Generate a daily report of the ingestion process.
    This function is designed to be used as an Airflow task.
    """
    logger.info("Starting daily report generation task...")
    
    try:
        fetch_results = context['task_instance'].xcom_pull(key='fetch_results', task_ids='fetch_daily_papers')
        
        failed_pdf_results = context['task_instance'].xcom_pull(task_ids='process_failed_pdfs')
        
        opensearch_results = context['task_instance'].xcom_pull(task_ids='create_opensearch_placeholders')
        
        report = {
            'date': context['ds'],
            "execution_time": datetime.now().isoformat(),
            "papers": {
                "fetched": fetch_results.get('papers_fetched', 0) if fetch_results else 0,
                "pdfs_downloaded": fetch_results.get('pdfs_downloaded', 0) if fetch_results else 0,
                "pdfs_parsed": fetch_results.get('pdfs_parsed', 0) if fetch_results else 0,
                "stored": fetch_results.get('papers_stored', 0) if fetch_results else 0,
            },
            "processing": {
                "processing_time_seconds": fetch_results.get('processing_time', 0) if fetch_results else 0,
                "errors": len(fetch_results.get('errors', [])) if fetch_results else 0,
                "failed_pdf_retries": failed_pdf_results.get('errors_logged', 0) if failed_pdf_results else 0,
            },
            "opensearch": {
                "placeholders_created": opensearch_results.get('papers_ready_for_indexing', 0) if opensearch_results else 0,
                "status": opensearch_results.get('status', 'unknown') if opensearch_results else 'unknown',
            }
        }   
        
        logger.info("=== DAILY ARXIV PROCESSING REPORT ===")
        logger.info(f"Date: {report['date']}")
        logger.info(f"Papers fetched: {report['papers']['fetched']}")
        logger.info(f"PDFs downloaded: {report['papers']['pdfs_downloaded']}")
        logger.info(f"PDFs parsed: {report['papers']['pdfs_parsed']}")
        logger.info(f"Papers stored: {report['papers']['stored']}")
        logger.info(f"Processing time: {report['processing']['processing_time_seconds']:.1f}s")
        logger.info(f"Errors encountered: {report['processing']['errors']}")
        logger.info(f"OpenSearch placeholders: {report['opensearch']['placeholders_created']}")
        logger.info("=== END REPORT ===")
    
    except Exception as e:
        error_msg = f"Error during daily report generation: {str(e)}"
        logger.error(error_msg)
        raise Exception(error_msg)