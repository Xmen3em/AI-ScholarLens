from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator

# Import task functions from separate module
from arxiv_ingestion.tasks import (
    fetch_daily_papers,
    generate_daily_report,
    index_to_opensearch,
    process_failed_pdfs,
    setup_environment,
)

# Default DAG arguments
default_args = {
    "owner": "arxiv-curator",
    "depends_on_past": False,
    "start_date": datetime(2025, 8, 8),
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=30),
    "catchup": False,
}

# Create the DAG
dag = DAG(
    "arxiv_paper_ingestion",
    default_args=default_args,
    description="Daily arXiv AI-category paper ingestion and processing pipeline",
    schedule="0 6 * * 1-5",  # Monday-Friday at 6 AM UTC (excludes weekends)
    max_active_runs=1,
    catchup=False,
    tags=["arxiv", "papers", "ingestion", "week2"],
)

# Task definitions
setup_task = PythonOperator(
    task_id="setup_environment",
    python_callable=setup_environment,
    dag=dag,
)

fetch_task = PythonOperator(
    task_id="fetch_daily_papers",
    python_callable=fetch_daily_papers,
    dag=dag,
)

retry_task = PythonOperator(
    task_id="process_failed_pdfs",
    python_callable=process_failed_pdfs,
    dag=dag,
)

index_task = PythonOperator(
    task_id="index_to_opensearch",
    python_callable=index_to_opensearch,
    dag=dag,
)

report_task = PythonOperator(
    task_id="generate_daily_report",
    python_callable=generate_daily_report,
    dag=dag,
)

cleanup_task = BashOperator(
    task_id="cleanup_temp_files",
    bash_command="""
    echo "Cleaning up temporary files..."
    # Remove PDFs older than 30 days to manage disk space
    find /tmp -name "*.pdf" -type f -mtime +30 -delete 2>/dev/null || true
    echo "Cleanup completed"
    """,
    dag=dag,
)

# Task dependencies
# Main pipeline: setup -> fetch -> (retry + index) -> report -> cleanup
setup_task >> fetch_task >> [retry_task, index_task] >> report_task >> cleanup_task
