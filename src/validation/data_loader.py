import sqlite3
import json
import ast
from collections import defaultdict
from typing import List, Dict, Any, Optional

# Import LOG_LEVEL from the config module
from .config_and_policies import LOG_LEVEL, DB_PATH

def parse_event_row(row: sqlite3.Row) -> Dict[str, Any]:
    """Converts a sqlite3.Row object to a dictionary and parses JSON string fields,
       with a fallback for Python literal strings."""
    event_dict = dict(row)
    json_fields_to_parse = ["agent_generated_payload", "tool_input", "tool_raw_response"]
    
    for field_name in json_fields_to_parse:
        if field_name in event_dict and isinstance(event_dict[field_name], str):
            value_str = event_dict[field_name].strip()
            if value_str.lower() == "null" or not value_str: # Handles "null" string or empty
                event_dict[field_name] = None
            else:
                try:
                    # First, try direct JSON parsing
                    event_dict[field_name] = json.loads(value_str)
                except json.JSONDecodeError:
                    try:
                        python_obj = ast.literal_eval(value_str)
                        event_dict[field_name] = python_obj
                    except (ValueError, SyntaxError, TypeError):
                        if LOG_LEVEL == "DEBUG":
                            print(f"Warning (parse_event_row): Could not parse field '{field_name}' for event id {event_dict.get('id')}. Value (truncated): {value_str[:100]}...")
    return event_dict


def fetch_and_group_telemetry() -> Dict[str, List[Dict[str, Any]]]:
    """Fetches all telemetry events from DB_PATH and groups them by session_id, sorted by timestamp."""
    sessions_data: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    conn: Optional[sqlite3.Connection] = None
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * 
            FROM experimenttelemetryevent 
            ORDER BY session_id ASC, timestamp ASC
        """)
        
        for row in cursor.fetchall():
            event = parse_event_row(row)
            sessions_data[event['session_id']].append(event)
            
    except sqlite3.Error as e:
        if LOG_LEVEL in ["INFO", "DEBUG"]:
            print(f"SQLite error when fetching telemetry: {e}")
    finally:
        if conn:
            conn.close()
            
    return sessions_data
