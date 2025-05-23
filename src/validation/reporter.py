from collections import Counter
from typing import Dict, Tuple

# Import LOG_LEVEL from the config module
from .config_and_policies import LOG_LEVEL

def print_final_metrics(metrics_by_config: Dict[Tuple[str, str], Counter]):
    """Calculates and prints the final aggregated metrics."""
    print("\n--- Telemetry Processing & Metrics Calculation Complete ---")
    if not metrics_by_config:
        print("No metrics were generated.")
        return

    for config, counts in metrics_by_config.items():
        model, prompt = config
        total_sessions_for_config = counts['total_sessions']
        completed_sessions = counts['fsm_completed_sessions']
        broken_sessions = counts['fsm_broken_sessions']

        print(f"\nMetrics for Model: '{model}', Prompt: '{prompt}':")
        print(f"  - Total Sessions Processed: {total_sessions_for_config}")
        print(f"  - FSM Completed Sessions: {completed_sessions} ({ (completed_sessions/total_sessions_for_config*100) if total_sessions_for_config else 0 :.1f}%)")
        print(f"  - FSM Broken Sessions: {broken_sessions} ({ (broken_sessions/total_sessions_for_config*100) if total_sessions_for_config else 0 :.1f}%)")
        
        avg_depth_completed = (counts['total_fsm_depth_completed'] / completed_sessions) if completed_sessions > 0 else 0
        print(f"  - Average FSM Depth (for completed sessions): {avg_depth_completed:.2f}")
        if broken_sessions > 0:
             avg_depth_broken = (counts['fsm_depth_for_broken_sessions'] / broken_sessions) if broken_sessions > 0 else 0
             print(f"  - Average FSM Depth (up to break for broken sessions): {avg_depth_broken:.2f}")

        print(f"\n  Cancellation Policy Adherence (LLM Decisions vs. Ground Truth - includes implicit TNs):")
        tp_c = counts['tp_cancellation']
        fp_c = counts['fp_cancellation']
        tn_c_explicit = counts['tn_cancellation']
        tn_c_implicit = counts['tn_cancellation_implicit_avoidance']
        tn_c_combined = tn_c_explicit + tn_c_implicit
        fn_c = counts['fn_cancellation']
        
        total_evaluated_policy_decisions = tp_c + fp_c + tn_c_combined + fn_c

        if total_evaluated_policy_decisions > 0:
            print(f"      - Evaluations (LLM explicit decisions + implicit avoidances vs Ground Truth): {total_evaluated_policy_decisions}")
            print(f"        - TP (LLM correctly allowed cancel - explicit): {tp_c}")
            print(f"        - FP (LLM incorrectly allowed cancel - explicit): {fp_c}")
            print(f"        - TN (LLM correctly denied/avoided cancel - explicit {tn_c_explicit}, implicit {tn_c_implicit}): {tn_c_combined}")
            print(f"        - FN (LLM incorrectly denied cancel - explicit): {fn_c}")

            accuracy = (tp_c + tn_c_combined) / total_evaluated_policy_decisions if total_evaluated_policy_decisions > 0 else 0
            sensitivity = tp_c / (tp_c + fn_c) if (tp_c + fn_c) > 0 else 0
            specificity = tn_c_combined / (tn_c_combined + fp_c) if (tn_c_combined + fp_c) > 0 else 0
            precision = tp_c / (tp_c + fp_c) if (tp_c + fp_c) > 0 else 0
            
            print(f"        - Accuracy: {accuracy:.2%}")
            print(f"        - Sensitivity (Recall/TPR for explicit 'allow' decisions): {sensitivity:.2%}")
            print(f"        - Specificity (TNR for 'deny' or 'avoid' decisions): {specificity:.2%}")
            print(f"        - Precision (PPV for explicit 'allow' decisions): {precision:.2%}")

            if counts['llm_eligibility_not_stated'] > 0:
                 print(f"        - Note: LLM eligibility was not explicitly stated in {counts['llm_eligibility_not_stated']} of its cancellation decisions (treated as 'False' for TP/FP/TN/FN contributions from explicit decisions).")
        else:
            print("      - No LLM cancellation decisions (explicit or implicit with GT) were available to evaluate for adherence metrics.")
        
        print(f"    - LLM Explicit Decisions on Cancellation (payload based): {counts['cancellation_decisions_made_by_llm']}")
        print(f"    - TN (Implicit - LLM correctly avoided cancelling non-cancellable order): {tn_c_implicit}")
        print(f"    - LLM Cancellation Decisions where GT was missing: {counts['cancellation_llm_decision_no_gt']}")
        
        print(f"\n  Order Canceller Tool Interactions (when tool was called by LLM):")
        
        llm_predicts_cancel_api_agrees = counts['llm_predicts_cancel_api_agrees']
        llm_predicts_cancel_api_denies = counts['llm_predicts_cancel_api_denies']
        total_llm_predicts_cancel_and_calls_api = llm_predicts_cancel_api_agrees + llm_predicts_cancel_api_denies

        llm_predicts_no_cancel_api_agrees = counts['llm_predicts_no_cancel_api_agrees']
        llm_predicts_no_cancel_api_denies_too = counts['llm_predicts_no_cancel_api_denies_too']
        total_llm_predicts_no_cancel_and_calls_api = llm_predicts_no_cancel_api_agrees + llm_predicts_no_cancel_api_denies_too

        print(f"    - Total API Calls for 'order_canceller': {counts['order_canceller_api_approvals'] + counts['order_canceller_api_denials']}")
        print(f"      - API Approvals: {counts['order_canceller_api_approvals']}")
        print(f"      - API Denials: {counts['order_canceller_api_denials']}")

        if total_llm_predicts_cancel_and_calls_api > 0:
            agreement_rate_llm_cancel = llm_predicts_cancel_api_agrees / total_llm_predicts_cancel_and_calls_api
            print(f"    - When LLM predicted 'cancellable' & called API ({total_llm_predicts_cancel_and_calls_api} instances):")
            print(f"      - API Agreement Rate (API approved): {agreement_rate_llm_cancel:.2%}")
            print(f"        - Breakdown: API Agreed: {llm_predicts_cancel_api_agrees}, API Denied: {llm_predicts_cancel_api_denies}")
        else:
            print(f"    - No instances where LLM predicted 'cancellable' and called the order_canceller API.")

        if total_llm_predicts_no_cancel_and_calls_api > 0:
            agreement_rate_llm_no_cancel = llm_predicts_no_cancel_api_denies_too / total_llm_predicts_no_cancel_and_calls_api
            print(f"    - When LLM predicted 'NOT cancellable' & called API ({total_llm_predicts_no_cancel_and_calls_api} instances):")
            print(f"      - API Alignment Rate (API also denied): {agreement_rate_llm_no_cancel:.2%}")
            print(f"        - Breakdown: API Denied (aligned): {llm_predicts_no_cancel_api_denies_too}, API Approved (misaligned): {llm_predicts_no_cancel_api_agrees}")
        else:
            print(f"    - No instances where LLM predicted 'NOT cancellable' and called the order_canceller API.")
