import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))

from golden_dataset import GOLDEN_INCIDENTS
from eval_graph_multi import eval_graph_multi
from seed_memory import SEED_INCIDENTS
from memory import reset_and_seed_memory
import tools
from run_evals import grade_incident

def run_all_evals_multi():
    reset_and_seed_memory(SEED_INCIDENTS)
    results = []

    for golden in GOLDEN_INCIDENTS:
        print(f"\n{'='*60}")
        print(f"Running {golden['id']}: {golden['incident']}")
        print('='*60)

        tools.set_incident(golden["id"])

        config = {"configurable": {"thread_id": golden["id"] + "-multi"}}
        result = eval_graph_multi.invoke({
            "incident": golden["incident"],
            "service": golden["service"],
            "past_incidents": [],
            "investigation_goal": "",
            "findings": [],
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

        results.append({"id": golden["id"], "passed": passed, "reason": reason})

    return results


def print_summary(results):
    print(f"\n\n{'='*60}")
    print("MULTI-AGENT EVAL SUMMARY")
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
    results = run_all_evals_multi()
    print_summary(results)