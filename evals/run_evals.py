import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))

from golden_dataset import GOLDEN_INCIDENTS
from eval_graph import eval_graph
import tools


def grade_incident(golden, agent_hypothesis, agent_enough_evidence, agent_proposed_action, hypothesis_history):
    hyp_lower = " ".join(hypothesis_history).lower()
    action_lower = agent_proposed_action.lower()

    if golden["expect_escalation"]:
        if "escalate" in action_lower:
            return True, "Correctly escalated instead of proposing a confident action"
        else:
            return False, "Agent proposed a confident action on a case that should have escalated"

    if "escalate" in action_lower:
        return False, "Agent escalated on a case that should have had a clear answer"

    for bad_word in golden["forbidden_keywords"]:
        if bad_word.lower() in hyp_lower:
            return False, f"Hypothesis contains forbidden phrase: '{bad_word}'"

    for good_word in golden["gold_cause_keywords"]:
        if good_word.lower() in hyp_lower:
            return True, f"Hypothesis correctly mentions '{good_word}'"

    return False, "Hypothesis did not mention any expected cause"


def run_all_evals():
    results = []

    for golden in GOLDEN_INCIDENTS:
        print(f"\n{'='*60}")
        print(f"Running {golden['id']}: {golden['incident']}")
        print('='*60)

        tools.set_incident(golden["id"])

        config = {"configurable": {"thread_id": golden["id"]}}
        result = eval_graph.invoke({
            "incident": golden["incident"],
            "service": golden["service"],
            "plan": "",
            "evidence": [],
            "hypothesis": "",
            "hypothesis_history": [],
            "enough_evidence": "",
            "iterations": 0,
            "proposed_action": "",
            "approved": ""
        }, config=config)

        passed, reason = grade_incident(
            golden,
            result["hypothesis"],
            result["enough_evidence"],
            result["proposed_action"],
            result["hypothesis_history"]
        )

        results.append({
            "id": golden["id"],
            "passed": passed,
            "reason": reason,
            "hypothesis": result["hypothesis"]
        })

    return results


def print_summary(results):
    print(f"\n\n{'='*60}")
    print("EVAL SUMMARY")
    print('='*60)

    passed_count = 0
    for r in results:
        status = "PASS" if r["passed"] else "FAIL"
        if r["passed"]:
            passed_count += 1
        print(f"[{status}] {r['id']}: {r['reason']}")

    total = len(results)
    print(f"\n{passed_count}/{total} passed ({round(100 * passed_count / total)}%)")


if __name__ == "__main__":
    results = run_all_evals()
    print_summary(results)