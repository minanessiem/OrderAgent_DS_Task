from collections import Counter
from typing import List, Dict, Any, Optional, Tuple

# Import necessary items from config_and_policies
from .config_and_policies import (
    LOG_LEVEL, 
    INITIAL_STATE_TYPE, 
    VALID_TRANSITIONS, 
    get_policy_ground_truth
)

def process_session_with_fsm(
    session_id: str,
    events: List[Dict[str, Any]],
    metrics_aggregator: Dict[Tuple[str, str], Counter]  # Note: Counter is directly from collections
):
    """Processes events for a single session using FSM logic and updates metrics_aggregator."""
    if LOG_LEVEL in ["INFO", "DEBUG"]:
        print(f"\n--- Processing Session ID: {session_id} ---")
    if not events:
        if LOG_LEVEL == "DEBUG":
            print(f"  [DEBUG {session_id}] No events in this session.")
        return

    model_prompt_config = (events[0].get("agent_model_name", "UnknownModel"),
                           events[0].get("system_prompt_name", "UnknownPrompt"))

    if model_prompt_config not in metrics_aggregator:
        metrics_aggregator[model_prompt_config] = Counter()

    metrics_aggregator[model_prompt_config]["total_sessions"] += 1

    session_fsm_depth = 0
    session_fsm_ok = True
    current_session_already_marked_broken = False
    previous_event_type: Optional[str] = None

    # State for current user turn's cancellation attempt
    turn_active_cancel_query = False
    turn_cancel_order_id: Optional[str] = None
    turn_order_details_for_gt: Optional[Dict[str, Any]] = None
    turn_gt_cancellable_status: Optional[bool] = None
    turn_gt_evaluation_timestamp: Optional[str] = None
    turn_llm_perceived_eligibility_for_tool_call: Optional[bool] = None
    turn_llm_made_explicit_cancellation_decision_this_turn = False

    if LOG_LEVEL == "DEBUG":
        print(f"  [DEBUG {session_id}] Initializing session. Model: {model_prompt_config[0]}, Prompt: {model_prompt_config[1]}")

    for i, event in enumerate(events):
        event_type = event['event_type']
        event_id = event.get('id', 'N/A')
        timestamp = event['timestamp']
        if LOG_LEVEL == "DEBUG":
            print(f"\n  [DEBUG {session_id}] Event {i+1} (ID: {event_id}, Type: {event_type}, Timestamp: {timestamp})")
            print(f"    [FSM_STATE {session_id}] Current FSM OK: {session_fsm_ok}, Prev Event Type: {previous_event_type}, Current Event Type: {event_type}")

        
        # Reset turn-specific cancellation state at the start of a new user query
        if event_type == "USER_QUERY_RECEIVED":
            if LOG_LEVEL == "DEBUG":
                print(f"    [TURN_RESET {session_id}] USER_QUERY_RECEIVED. Resetting turn-specific cancellation variables.")
            if turn_active_cancel_query and turn_gt_cancellable_status is False and not turn_llm_made_explicit_cancellation_decision_this_turn:
                 if LOG_LEVEL == "DEBUG":
                     print(f"    [IMPLICIT_TN_CHECK {session_id}] Previous turn had active_cancel_query, GT was False, and LLM made no explicit True cancel decision.")
                 metrics_aggregator[model_prompt_config]["tn_cancellation_implicit_avoidance"] += 1
                 if LOG_LEVEL == "DEBUG":
                     print(f"      [METRIC_UPDATE {session_id}] Incremented tn_cancellation_implicit_avoidance.")

            turn_active_cancel_query = "cancel" in event.get('user_query', "").lower()
            turn_cancel_order_id = None
            turn_order_details_for_gt = None
            turn_gt_cancellable_status = None
            turn_gt_evaluation_timestamp = None
            turn_llm_perceived_eligibility_for_tool_call = None
            turn_llm_made_explicit_cancellation_decision_this_turn = False
            if LOG_LEVEL == "DEBUG":
                print(f"    [TURN_RESET {session_id}] Query: '{event.get('user_query', '')}', turn_active_cancel_query: {turn_active_cancel_query}")

        if not session_fsm_ok:
            if LOG_LEVEL == "DEBUG":
                print(f"    [FSM_STATE {session_id}] Session FSM already broken. Skipping further FSM-dependent processing for this event.")
            # Continue to the next event even if FSM is broken, to allow logging/counting of all events if desired
            # but specific FSM-dependent metrics won't be processed.
            # No 'continue' here if you want to still try to parse non-FSM data from broken sessions.
            # For this refactoring, we'll keep the original logic of skipping FSM parts.
            if current_session_already_marked_broken: # only count depth once
                 pass # already handled
            # The original code had 'continue' right after this check for not session_fsm_ok.
            # We need to decide if any further processing happens for events in a broken FSM session.
            # For now, replicating original behaviour:
            continue


        # FSM Validation
        if i == 0:
            if event_type != INITIAL_STATE_TYPE:
                session_fsm_ok = False
                if LOG_LEVEL == "DEBUG":
                    print(f"    [FSM_VALIDATION {session_id}] FSM Broken: Session does not start with '{INITIAL_STATE_TYPE}'. Found '{event_type}'.")
        elif previous_event_type:
            if previous_event_type not in VALID_TRANSITIONS or \
               event_type not in VALID_TRANSITIONS.get(previous_event_type, []):
                session_fsm_ok = False
                if LOG_LEVEL == "DEBUG":
                    print(f"    [FSM_VALIDATION {session_id}] FSM Broken: Invalid transition from '{previous_event_type}' to '{event_type}'. Allowed: {VALID_TRANSITIONS.get(previous_event_type, [])}")

        if not session_fsm_ok:
            if not current_session_already_marked_broken:
                metrics_aggregator[model_prompt_config]["fsm_broken_sessions"] += 1
                current_session_already_marked_broken = True
                if LOG_LEVEL in ["INFO", "DEBUG"]: 
                     print(f"    [INFO {session_id}] Session FSM marked as broken.")
                if LOG_LEVEL == "DEBUG":
                    print(f"      [METRIC_UPDATE {session_id}] Incremented fsm_broken_sessions.")
            metrics_aggregator[model_prompt_config]["fsm_depth_for_broken_sessions"] += session_fsm_depth # Add depth *up to* the break
            if LOG_LEVEL == "DEBUG":
                print(f"      [METRIC_UPDATE {session_id}] Added {session_fsm_depth} to fsm_depth_for_broken_sessions. Total now: {metrics_aggregator[model_prompt_config]['fsm_depth_for_broken_sessions']}")
            continue # Stop FSM-dependent processing for this and subsequent events in broken session

        session_fsm_depth += 1
        if LOG_LEVEL == "DEBUG":
            print(f"    [FSM_STATE {session_id}] FSM OK. Incremented session_fsm_depth to {session_fsm_depth}.")


        # Cancellation Metrics Logic (ensure this is only processed if FSM is OK)
        if turn_active_cancel_query and not turn_cancel_order_id and event.get("order_id_identified"):
            turn_cancel_order_id = event.get("order_id_identified")
            if LOG_LEVEL == "DEBUG":
                print(f"    [CANCEL_LOGIC {session_id}] Active cancel query. Set turn_cancel_order_id to: {turn_cancel_order_id} from event's 'order_id_identified'.")

        if event_type == "AGENT_TOOL_EXECUTED" and event.get("tool_name") == "order_tracker" and turn_active_cancel_query:
            if LOG_LEVEL == "DEBUG":
                print(f"    [CANCEL_LOGIC {session_id}] Event is AGENT_TOOL_EXECUTED for 'order_tracker' during active cancel query.")
            tool_raw_resp = event.get("tool_raw_response")
            if isinstance(tool_raw_resp, dict) and tool_raw_resp.get("order_id") == turn_cancel_order_id:
                turn_order_details_for_gt = tool_raw_resp
                turn_gt_evaluation_timestamp = event.get("timestamp")
                if LOG_LEVEL == "DEBUG":
                    print(f"    [CANCEL_LOGIC {session_id}] Matched tool_raw_response order_id '{tool_raw_resp.get('order_id')}' with turn_cancel_order_id '{turn_cancel_order_id}'.")
                    print(f"      Details for GT: {turn_order_details_for_gt}")
                    print(f"      GT Evaluation Timestamp: {turn_gt_evaluation_timestamp}")
                if turn_order_details_for_gt and turn_gt_evaluation_timestamp:
                    turn_gt_cancellable_status = get_policy_ground_truth(turn_order_details_for_gt, turn_gt_evaluation_timestamp)
                    if LOG_LEVEL == "DEBUG":
                        print(f"    [CANCEL_LOGIC {session_id}] Ground Truth for cancellability: {turn_gt_cancellable_status}")
            elif LOG_LEVEL == "DEBUG":
                print(f"    [CANCEL_LOGIC {session_id}] Order_tracker response did not match turn_cancel_order_id ({turn_cancel_order_id}) or not a dict. Tool response order ID: {tool_raw_resp.get('order_id') if isinstance(tool_raw_resp, dict) else 'N/A'}")


        if event_type == "AGENT_DECISION_INTENT" and turn_active_cancel_query and turn_cancel_order_id == event.get("order_id_identified"):
            if LOG_LEVEL == "DEBUG":
                print(f"    [CANCEL_LOGIC {session_id}] Event is AGENT_DECISION_INTENT, active cancel query, and order ID ({event.get('order_id_identified')}) matches turn_cancel_order_id ({turn_cancel_order_id}).")
            llm_payload = event.get("agent_generated_payload")
            if isinstance(llm_payload, dict) and llm_payload.get("action_under_consideration") == "order_cancellation":
                turn_llm_made_explicit_cancellation_decision_this_turn = True 
                if LOG_LEVEL == "DEBUG":
                    print(f"    [CANCEL_LOGIC {session_id}] LLM action_under_consideration is 'order_cancellation'. Marked turn_llm_made_explicit_cancellation_decision_this_turn = True.")
                metrics_aggregator[model_prompt_config]["cancellation_decisions_made_by_llm"] +=1
                llm_perceived_eligibility = llm_payload.get("perceived_eligibility_for_action")
                turn_llm_perceived_eligibility_for_tool_call = llm_perceived_eligibility
                if LOG_LEVEL == "DEBUG":
                    print(f"      LLM Payload: {llm_payload}")
                    print(f"      LLM perceived_eligibility: {llm_perceived_eligibility}. Stored as turn_llm_perceived_eligibility_for_tool_call.")
                    print(f"      [METRIC_UPDATE {session_id}] Incremented cancellation_decisions_made_by_llm.")

                if llm_perceived_eligibility is None:
                     metrics_aggregator[model_prompt_config]["llm_eligibility_not_stated"] += 1
                     if LOG_LEVEL == "DEBUG": print(f"      [METRIC_UPDATE {session_id}] Incremented llm_eligibility_not_stated.")

                llm_decision_bool = False if llm_perceived_eligibility is None else llm_perceived_eligibility
                if LOG_LEVEL == "DEBUG": print(f"      LLM decision (bool for comparison): {llm_decision_bool}")

                if turn_gt_cancellable_status is not None:
                    if LOG_LEVEL == "DEBUG": print(f"    [CANCEL_LOGIC {session_id}] Comparing LLM decision ({llm_decision_bool}) with GT ({turn_gt_cancellable_status}).")
                    metrics_aggregator[model_prompt_config]["cancellation_evaluations_vs_gt_possible"] += 1 # This counts explicit decisions where GT is available
                    if LOG_LEVEL == "DEBUG": print(f"      [METRIC_UPDATE {session_id}] Incremented cancellation_evaluations_vs_gt_possible.")
                    
                    if llm_decision_bool is True and turn_gt_cancellable_status is True:
                        metrics_aggregator[model_prompt_config]["tp_cancellation"] += 1
                        if LOG_LEVEL == "DEBUG": print(f"        [METRIC_UPDATE {session_id}] TP Cancellation.")
                    elif llm_decision_bool is True and turn_gt_cancellable_status is False:
                        metrics_aggregator[model_prompt_config]["fp_cancellation"] += 1
                        if LOG_LEVEL == "DEBUG": print(f"        [METRIC_UPDATE {session_id}] FP Cancellation.")
                    elif llm_decision_bool is False and turn_gt_cancellable_status is False:
                        metrics_aggregator[model_prompt_config]["tn_cancellation"] += 1
                        if LOG_LEVEL == "DEBUG": print(f"        [METRIC_UPDATE {session_id}] TN Cancellation.")
                    elif llm_decision_bool is False and turn_gt_cancellable_status is True:
                        metrics_aggregator[model_prompt_config]["fn_cancellation"] += 1
                        if LOG_LEVEL == "DEBUG": print(f"        [METRIC_UPDATE {session_id}] FN Cancellation.")
                else:
                    metrics_aggregator[model_prompt_config]["cancellation_llm_decision_no_gt"] += 1
                    if LOG_LEVEL == "DEBUG": print(f"    [CANCEL_LOGIC {session_id}] Ground truth not available for comparison. Incremented cancellation_llm_decision_no_gt.")
            elif isinstance(llm_payload, dict) and LOG_LEVEL == "DEBUG":
                 print(f"    [CANCEL_LOGIC {session_id}] LLM action_under_consideration is '{llm_payload.get('action_under_consideration')}', not 'order_cancellation'. Skipping TP/FP for this decision.")
            elif LOG_LEVEL == "DEBUG":
                print(f"    [CANCEL_LOGIC {session_id}] LLM payload is not a dict or missing for AGENT_DECISION_INTENT. Payload: {llm_payload}")
        
        if event_type == "AGENT_FINAL_RESPONSE":
            if LOG_LEVEL == "DEBUG": print(f"    [TURN_END_CHECK {session_id}] AGENT_FINAL_RESPONSE encountered.")
            if turn_active_cancel_query and turn_gt_cancellable_status is False and not turn_llm_made_explicit_cancellation_decision_this_turn:
                 if LOG_LEVEL == "DEBUG": print(f"    [IMPLICIT_TN_CHECK {session_id}] Current turn had active_cancel_query, GT was False ({turn_gt_cancellable_status}), and LLM made no explicit 'order_cancellation' decision payload.")
                 metrics_aggregator[model_prompt_config]["tn_cancellation_implicit_avoidance"] += 1
                 if LOG_LEVEL == "DEBUG": print(f"      [METRIC_UPDATE {session_id}] Incremented tn_cancellation_implicit_avoidance.")
                 turn_llm_made_explicit_cancellation_decision_this_turn = True


        if event_type == "AGENT_TOOL_EXECUTED" and event.get("tool_name") == "order_canceller":
            if LOG_LEVEL == "DEBUG": print(f"    [TOOL_INTERACTION {session_id}] Event is AGENT_TOOL_EXECUTED for 'order_canceller'.")
            tool_success_direct = event.get("tool_response_success")
            tool_raw_resp = event.get("tool_raw_response")
            derived_tool_success: Optional[bool] = None
            if tool_success_direct is not None:
                derived_tool_success = tool_success_direct
                if LOG_LEVEL == "DEBUG": print(f"      Using direct tool_response_success: {derived_tool_success}")
            elif isinstance(tool_raw_resp, dict) and 'success' in tool_raw_resp:
                derived_tool_success = tool_raw_resp.get('success')
                if LOG_LEVEL == "DEBUG": print(f"      Derived tool_response_success from tool_raw_response: {derived_tool_success}. Raw response 'success' field: {tool_raw_resp.get('success')}")
            elif LOG_LEVEL == "DEBUG":
                print(f"      tool_response_success is None AND could not derive from tool_raw_response. Raw response: {tool_raw_resp}")
            
            if LOG_LEVEL == "DEBUG":
                print(f"      Effective tool_success for logic: {derived_tool_success}")
            if LOG_LEVEL == "DEBUG": # Moved this specific log to be conditional
                 print(f"      LLM's belief before this tool call (turn_llm_perceived_eligibility_for_tool_call): {turn_llm_perceived_eligibility_for_tool_call}")


            if derived_tool_success is True:
                metrics_aggregator[model_prompt_config]["order_canceller_api_approvals"] += 1
                if LOG_LEVEL == "DEBUG": print(f"      [METRIC_UPDATE {session_id}] API Approved. Incremented order_canceller_api_approvals.")
                if turn_llm_perceived_eligibility_for_tool_call is True:
                    metrics_aggregator[model_prompt_config]["llm_predicts_cancel_api_agrees"] += 1
                    if LOG_LEVEL == "DEBUG": print(f"        [METRIC_UPDATE {session_id}] LLM predicted cancellable, API agreed.")
                elif turn_llm_perceived_eligibility_for_tool_call is False: # LLM thought no, API said yes
                    metrics_aggregator[model_prompt_config]["llm_predicts_no_cancel_api_agrees"] +=1 # API approved despite LLM predicting no_cancel
                    if LOG_LEVEL == "DEBUG": print(f"        [METRIC_UPDATE {session_id}] LLM predicted NOT cancellable, but API approved.")
                # If turn_llm_perceived_eligibility_for_tool_call is None, we don't count it in these sub-categories
            elif derived_tool_success is False:
                metrics_aggregator[model_prompt_config]["order_canceller_api_denials"] += 1
                if LOG_LEVEL == "DEBUG": print(f"      [METRIC_UPDATE {session_id}] API Denied. Incremented order_canceller_api_denials.")
                if turn_llm_perceived_eligibility_for_tool_call is True: # LLM thought yes, API said no
                    metrics_aggregator[model_prompt_config]["llm_predicts_cancel_api_denies"] += 1
                    if LOG_LEVEL == "DEBUG": print(f"        [METRIC_UPDATE {session_id}] LLM predicted cancellable, but API denied.")
                elif turn_llm_perceived_eligibility_for_tool_call is False: # LLM thought no, API also said no
                     metrics_aggregator[model_prompt_config]["llm_predicts_no_cancel_api_denies_too"] +=1
                     if LOG_LEVEL == "DEBUG": print(f"        [METRIC_UPDATE {session_id}] LLM predicted NOT cancellable, API also denied.")
                # If turn_llm_perceived_eligibility_for_tool_call is None, we don't count it in these sub-categories
            elif LOG_LEVEL == "DEBUG": 
                 print(f"      [TOOL_INTERACTION {session_id}] Effective tool_success for order_canceller is None or non-boolean. Not counted in API approvals/denials.")
        previous_event_type = event_type

    # End of loop for events in a session
    if LOG_LEVEL == "DEBUG": print(f"  [DEBUG {session_id}] Finished processing events for session. Last event type: {previous_event_type}")
    
    # Final implicit TN check if session ends before next USER_QUERY_RECEIVED (e.g. if last event is AGENT_FINAL_RESPONSE)
    # This logic was slightly duplicated, ensuring it's correctly placed after loop or at AGENT_FINAL_RESPONSE
    # The AGENT_FINAL_RESPONSE check inside the loop handles it if it's not the very last event.
    # This handles if the loop ends due to no more events and previous was AGENT_FINAL_RESPONSE.
    # This check for implicit TN *after* the loop is redundant if the AGENT_FINAL_RESPONSE within the loop handles it and sets turn_llm_made_explicit_cancellation_decision_this_turn = True
    # However, to be safe and match original logic's intent of catching end-of-session TNs:
    if not turn_llm_made_explicit_cancellation_decision_this_turn and \
       turn_active_cancel_query and \
       turn_gt_cancellable_status is False:
        if LOG_LEVEL == "DEBUG": print(f"    [IMPLICIT_TN_CHECK_POST_LOOP {session_id}] Session ended. Active_cancel_query, GT was False, and LLM made no explicit 'order_cancellation' decision payload in the last turn.")
        # metrics_aggregator[model_prompt_config]["tn_cancellation_implicit_avoidance"] += 1 # This might double count if already handled by USER_QUERY or FINAL_RESPONSE
        # For safety, the original structure implicitly handled this by resetting at USER_QUERY_RECEIVED for the *next* turn, or by FINAL_RESPONSE check.
        # Let's rely on the in-loop checks for now to avoid double counting.
        pass


    if LOG_LEVEL == "DEBUG":
        print(f"    [FSM_STATE {session_id}] Final FSM OK for session: {session_fsm_ok}")
        print(f"    [FSM_STATE {session_id}] Final previous_event_type for session: {previous_event_type}")

    if session_fsm_ok :
        metrics_aggregator[model_prompt_config]["total_fsm_depth_completed"] += session_fsm_depth
        if LOG_LEVEL == "DEBUG": print(f"  [METRIC_UPDATE {session_id}] Session FSM OK. Added {session_fsm_depth} to total_fsm_depth_completed. Total now: {metrics_aggregator[model_prompt_config]['total_fsm_depth_completed']}")
        if previous_event_type == "AGENT_FINAL_RESPONSE":
            metrics_aggregator[model_prompt_config]["fsm_completed_sessions"] += 1
            if LOG_LEVEL == "DEBUG": print(f"  [METRIC_UPDATE {session_id}] Session ended with AGENT_FINAL_RESPONSE. Incremented fsm_completed_sessions.")
        elif LOG_LEVEL == "DEBUG": 
            print(f"  [METRIC_UPDATE {session_id}] Session FSM OK but did not end with AGENT_FINAL_RESPONSE (ended with {previous_event_type}). Not counted as 'fsm_completed_sessions'.")
    
    if LOG_LEVEL in ["INFO", "DEBUG"]:
        print(f"--- Finished Processing Session ID: {session_id} ---")
