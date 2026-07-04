from datetime import datetime, timedelta
import sys
from pathlib import Path

# Add project root to path so tasks can import src packages
project_root = str(Path(__file__).resolve().parent.parent)
if project_root not in sys.path:
    sys.path.append(project_root)

from airflow import DAG
from airflow.operators.python import PythonOperator

# Import pipeline functions
from src.pipeline.ingest_bronze import run_ingestion
from src.pipeline.clean_silver import process_bronze_to_silver
from src.pipeline.analyze_gold import run_gold_analysis

# Default arguments for the Airflow tasks
default_args = {
    "owner": "data_science_team",
    "depends_on_past": False,
    "start_date": datetime(2026, 1, 1),
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

def run_ingest_wrapper(**context):
    """Wrapper function for ingestion task with Airflow logging."""
    print("Starting Bronze Ingestion (openFDA Extract)...")
    run_ingestion(max_records_per_drug=1000)
    print("Bronze Ingestion completed.")

def run_clean_wrapper(**context):
    """Wrapper function for cleaning task with Airflow logging."""
    print("Starting Silver Cleaning (Flattening & Deduplication)...")
    process_bronze_to_silver()
    print("Silver Cleaning completed.")

def run_analyze_wrapper(**context):
    """Wrapper function for gold analysis task with Airflow logging."""
    print("Starting Gold Analysis (PRR/ROR Calculation & SQL Load)...")
    run_gold_analysis()
    print("Gold Analysis and Database loading completed.")

# Define the DAG
with DAG(
    "faersight_drug_safety_pipeline",
    default_args=default_args,
    description="Orchestrates the Bronze-Silver-Gold FAERS/FAERSight drug safety signal pipeline",
    schedule_interval="@weekly",  # FAERS is updated quarterly, weekly checks check for delta ingestion
    catchup=False,
    tags=["pharmacovigilance", "medallion", "openfda", "faersight"],
) as dag:

    ingest_task = PythonOperator(
        task_id="ingest_bronze",
        python_callable=run_ingest_wrapper,
    )

    clean_task = PythonOperator(
        task_id="clean_silver",
        python_callable=run_clean_wrapper,
    )

    analyze_task = PythonOperator(
        task_id="analyze_gold",
        python_callable=run_analyze_wrapper,
    )

    # Set up task dependencies
    ingest_task >> clean_task >> analyze_task
