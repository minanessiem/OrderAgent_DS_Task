from collections import defaultdict, Counter
from typing import Dict, Tuple

# Import LOG_LEVEL from config_and_policies to make it accessible
from .config_and_policies import LOG_LEVEL, DB_PATH
from .data_loader import fetch_and_group_telemetry
from .fsm_processor import process_session_with_fsm
from .reporter import print_final_metrics

def main_telemetry_analysis_pipeline():
    """Main function to fetch, group, process telemetry data, and report metrics."""
    if LOG_LEVEL in ["INFO", "DEBUG"]:
        print(f"Starting telemetry analysis pipeline...")
        print(f"Fetching telemetry data from: {DB_PATH}")
    
    grouped_telemetry = fetch_and_group_telemetry() # DB_PATH is used internally by the function
    
    if not grouped_telemetry:
        if LOG_LEVEL in ["INFO", "DEBUG"]:
            print("No telemetry data found or an error occurred during fetching. Exiting.")
        return

    if LOG_LEVEL in ["INFO", "DEBUG"]:
        print(f"Found data for {len(grouped_telemetry)} sessions.")
    
    sorted_session_ids = sorted(grouped_telemetry.keys())

    # Initialize metrics_by_config here, as it's passed around
    metrics_by_config: Dict[Tuple[str, str], Counter] = defaultdict(Counter)

    for session_id in sorted_session_ids:
        process_session_with_fsm(session_id, grouped_telemetry[session_id], metrics_by_config)
    
    print_final_metrics(metrics_by_config)

if __name__ == "__main__":
    main_telemetry_analysis_pipeline()
