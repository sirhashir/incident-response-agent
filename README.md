# Incident Response Agent

An AI agent that investigates production incidents the way an on-call engineer would. It plans an investigation, gathers evidence using tools, reasons about root cause, and proposes a remediation. It always pauses for human approval before anything that could affect production. When it isn't confident, it says so and escalates instead of guessing.

Built entirely on **local LLMs (Ollama)**, so the whole system runs at zero API cost.

## Why this project

Most "AI agent" portfolio projects are single-shot RAG chatbots. This one covers the harder, more production-relevant patterns: agentic control flow (the agent decides its own next step, not a fixed pipeline), real tool use, a hard safety boundary (human approval before any action), persistent memory across runs, and evaluation. An agent that "looks fine when you try it" isn't proven to work. This project includes an adversarial eval suite specifically to find where it breaks.

## What it actually does

1. **Recalls** past incidents for the affected service from Postgres and includes them as context
2. **Plans** an investigation using an LLM
3. **Acts**, dynamically picking a tool (`fetch_logs`, `get_deploy_history`) based on what's already been checked, not a fixed script
4. **Reasons** over accumulated evidence, forms a hypothesis, and self-assesses whether it has enough to act
5. **Loops** back to gather more evidence if not confident, bounded by a hard iteration cap as a safety net against infinite loops
6. **Proposes** a concrete remediation, or explicitly escalates with "insufficient evidence" if it was never confident, rather than inventing a plausible-sounding fix
7. **Pauses** via LangGraph's `interrupt`/`Command(resume=...)` mechanism and waits for a human to approve or reject before anything happens
8. **Saves** the resolved incident to Postgres so future investigations on the same service start with relevant history

## Tech stack

- **Python** and **LangGraph** for agent orchestration, state graphs, conditional routing, and human-in-the-loop interrupts
- **Ollama** (`llama3.1:8b`), a local LLM with zero API cost, fully offline-capable
- **PostgreSQL** (Docker) for persistent incident memory
- **psycopg** as the Postgres driver
- A custom eval harness, no external eval framework. See the Evaluation section for why.

## Evaluation

The eval suite is the part of this project I'd point to first.

**10 hand-written, adversarial golden incidents.** Not just varied surface details, each one is designed to trip up a specific failure mode:
- A downstream-dependency case (don't blame the victim service)
- A deploy-correlation case (root cause only visible via `get_deploy_history`)
- A red-herring case (a loud but irrelevant error alongside the real, time-correlated cause)
- Two "insufficient evidence" cases where the correct answer is to escalate, not guess
- A cascading-failure case (distinguish root cause from downstream symptoms)
- A correlation-vs-causation trap (a deploy happened right before the incident, but isn't the cause)
- A clean control case (should always pass; if it doesn't, something is broken, not just hard)

**Grading is deterministic, not LLM-as-judge.** With an 8B local model doing the reasoning, using another LLM to grade that reasoning would add noise without a way to know whether a failure was the agent or the judge. Instead, each golden case defines required and forbidden keywords and an expected escalation behavior, checked in code.

**What the eval process actually found, across three iterations:**

Run 1: 10/10 (100%). Grading was too lenient to catch real mistakes. A meaningless result.

Run 2: 3/10 (30%). Tightened grading to check the agent's actual behavior (did it escalate appropriately?) instead of just an internal flag. This exposed that the model almost never self-terminated the reasoning loop on its own. It relied on the hard iteration cap in 9 of 10 cases, even on clear-cut incidents.

Run 3: 7/10 (70%). Root-caused the under-confidence to a prompt-framing bias: asking "are you confident" invites hedging from a small model. Reframed the question to "is this well-supported enough to act on." This fixed self-termination on 8 of 10 cases, but reintroduced false confidence on the two intentionally ambiguous cases. A precision/recall tradeoff, not a clean win.

This progression, not the final number, is the real result. It shows the eval suite doing its job: finding a real, specific, fixable problem, and then finding the boundary of that fix.

**Two further findings from adding a third tool (`query_metrics`):**

The tool was initially wired into the code but never added to the LLM's tool-selection prompt, so it was silently unreachable. Once added, `query_metrics` became the model's preferred first choice in most cases. This surfaced a real behavior worth naming: the model treats numeric metrics as inherently suspicious, producing hypotheses like "likely a CPU spike" even when the underlying fixture data was unremarkable. This is a mild hallucination pattern specific to numeric evidence, distinct from the earlier confidence-framing issue.

Separately, the grader was found to check only the final hypothesis string, while `reason_node` overwrites that field on each loop iteration. A correct diagnosis reached on an earlier pass could be lost if a later pass rephrased it without the exact grading keywords. Fixed by accumulating a hypothesis history across iterations and grading against the full trail instead of just the last value. This also surfaced a second, smaller issue: the golden dataset's keyword list for one case was too narrow, rejecting a correct diagnosis phrased as "method not found exception" because it didn't contain the literal word "deploy." Fixed by broadening accepted phrasings to match how the model actually describes a correct root cause, not just one expected wording.

## Known limitations

- Only two evidence-gathering tools. Once both are used, the agent repeats one rather than escalating for a third data source (a `query_metrics` tool would close this gap, see Roadmap)
- Keyword-based grading can be fooled by a hypothesis that names the right cause while tangled up with an irrelevant one (documented in the eval findings above rather than papered over)
- Recall is exact-match on service name, not semantic similarity
- Single agent, no specialization or delegation yet

## Roadmap

- Third tool (`query_metrics`) to reduce repeat tool calls and give the agent a genuine third investigative path
- Multi-agent orchestration, a supervisor delegating to a specialist agent for deep log analysis
- Langfuse tracing for full run observability
- Real integrations (Datadog, Kubernetes API) in place of fixture-based tools

## Running it

Start Postgres in Docker:
`docker run --name incident-db -e POSTGRES_PASSWORD=devpassword -e POSTGRES_DB=incidents -p 5434:5432 -d postgres:16`

Pull and start Ollama:
`ollama pull llama3.1:8b`
`ollama serve`

Set up Python:
`python -m venv venv`
`venv\Scripts\activate`
`pip install -r requirements.txt`

Copy `.env.example` to `.env` and fill in your DB password.

Run the agent interactively:
`python src/agent.py`

Run the eval suite:
`python evals/run_evals.py`

## Project structure

`fixtures/` holds fake log and deploy data per incident, used by tools and evals.

`learning/` holds the phase-by-phase build history, from a two-node hello-world graph to the full reasoning loop.

`src/` holds the actual agent: tools.py, memory.py, agent.py.

`evals/` holds the golden dataset, eval graph, grader, and results.

The `learning/` folder is left in on purpose. It's the incremental path to the full agent, and shows the reasoning behind each piece rather than just the final result.
