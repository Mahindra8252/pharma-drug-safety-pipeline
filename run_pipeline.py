import argparse
import logging
import sys
from src.pipeline.ingest_bronze import run_ingestion
from src.pipeline.clean_silver import process_bronze_to_silver
from src.pipeline.analyze_gold import run_gold_analysis

# Setup logging configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("pipeline_runner")

def main():
    parser = argparse.ArgumentParser(
        description="Pharma Drug-Safety Pipeline Runner (Medallion Architecture)"
    )
    
    parser.add_argument(
        "--step",
        choices=["all", "ingest", "clean", "analyze"],
        default="all",
        help="Pipeline step to run (default: all)"
    )
    
    parser.add_argument(
        "--limit",
        type=int,
        default=1000,
        help="Max records to ingest per drug (default: 1000)"
    )
    
    args = parser.parse_args()
    
    try:
        if args.step in ["all", "ingest"]:
            logger.info("=== STEP 1: BRONZE INGESTION (openFDA Extract) ===")
            run_ingestion(max_records_per_drug=args.limit)
            
        if args.step in ["all", "clean"]:
            logger.info("=== STEP 2: SILVER CLEANING (Flatten & Deduplicate) ===")
            process_bronze_to_silver()
            
        if args.step in ["all", "analyze"]:
            logger.info("=== STEP 3: GOLD ANALYSIS (PRR/ROR Calculation & SQL Load) ===")
            run_gold_analysis()
            
        logger.info("=== PIPELINE RUN COMPLETE ===")
        
    except Exception as e:
        logger.error(f"Pipeline execution failed: {str(e)}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
