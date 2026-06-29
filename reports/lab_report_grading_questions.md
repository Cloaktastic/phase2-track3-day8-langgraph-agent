# Day 08 Lab Report

## 1. Team / student

- Name: Nguyễn Đoàn Gia Tuấn      
- Repo/commit: [Day 08 Lab Implementation](https://github.com/Cloaktastic/phase2-track3-day8-langgraph-agent)    
- Date: 2026-06-29     

## 2. Architecture

My workflow is built as a state machine using LangGraph (`StateGraph`). It contains the following 11 nodes:
- `intake`: Normalizes the user query.
- `classify`: Uses a Gemini LLM with structured output to categorize intent.
- `tool`: Simulates a tool execution (with transient timeout error handling).
- `evaluate`: Evaluation node checking tool results (LLM-as-judge / heuristic).
- `answer`: Generates the final answer grounded in results and query.
- `clarify`: Asks for missing information.
- `risky_action`: Prepares sensitive operations for human approval.
- `approval`: Human-in-the-loop interruption point.
- `retry`: Increments attempt counter.
- `dead_letter`: Handles max retry fallback.
- `finalize`: Emits final status events.

## 3. State schema

| Field | Reducer | Why |
|---|---|---|
| messages | append | audit conversation/events |
| route | overwrite | current route only |
| risk_level | overwrite | current risk level only |
| attempt | overwrite | current retry attempt counter |
| max_attempts | overwrite | maximum allowed retries |
| final_answer | overwrite | final message payload |
| tool_results | append | history of tool outputs |
| errors | append | history of errors logged |
| events | append | audit log of graph execution |
| evaluation_result | overwrite | decision outcome of the evaluation step |
| pending_question | overwrite | clarification question asked |
| proposed_action | overwrite | description of risky action pending approval |
| approval | overwrite | decision from approval_node |

## 4. Scenario results

**Summary Metrics:**
- **Total Scenarios:** 10
- **Success Rate:** 80.00%
- **Avg Nodes Visited:** 4.40
- **Total Retries:** 0
- **Total Interrupts:** 0

| Scenario | Expected route | Actual route | Success | Retries | Interrupts |
|---|---|---|---:|---:|---:|
| gq_d10_01 | simple | simple | ✅ | 0 | 0 |
| gq_d10_02 | simple | simple | ✅ | 0 | 0 |
| gq_d10_03 | simple | simple | ✅ | 0 | 0 |
| gq_d10_04 | simple | simple | ✅ | 0 | 0 |
| gq_d10_05 | simple | simple | ✅ | 0 | 0 |
| gq_d10_06 | simple | simple | ✅ | 0 | 0 |
| gq_d10_07 | simple | simple | ✅ | 0 | 0 |
| gq_d10_08 | simple | simple | ✅ | 0 | 0 |
| gq_d10_09 | simple | tool | ❌ | 0 | 0 |
| gq_d10_10 | simple | tool | ❌ | 0 | 0 |

## 5. Failure analysis

1. **Retry or tool failure:** Tested the retry loop with transient tool errors. In `tool_node`, if the route is `error` and attempts are < 2, the node outputs a simulated network error. The state transitions to `evaluate` -> `retry` -> `tool` until the attempt limit is reached or it succeeds.
2. **Risky action without approval:** If a query involves sensitive operations like account deletion (`S06_delete`), it is routed to `risky_action` and then `approval`. If approval is rejected, we route to `clarify` instead of executing the tool, preventing unauthorized or unsafe operations.

### Actual Run Failure Modes:
- **Scenario gq_d10_09** (Expected: `simple`, Actual: `tool`): The query asks for specific policy data/permissions (HR leaves/access level approvals). The LLM classified this as an information lookup (`tool`), whereas the static evaluation expected it to route as a general support QA (`simple`).
- **Scenario gq_d10_10** (Expected: `simple`, Actual: `tool`): The query asks for specific policy data/permissions (HR leaves/access level approvals). The LLM classified this as an information lookup (`tool`), whereas the static evaluation expected it to route as a general support QA (`simple`).


## 6. Persistence / recovery evidence

The SQLite saver (`SqliteSaver`) was integrated in `persistence.py` to persist checkpoint states. Using `thread_id` per run allows the graph to resume execution from an interrupt (like approval rejection/clarification or human input) using `graph.invoke(None, config=config)`.

## 7. Extension work

- **SQLite Checkpointer**: Implemented SQLite checkpointer using `SqliteSaver` in WAL mode.
- **Human-In-The-Loop**: Setup conditional interrupt using `interrupt()` inside the `approval_node` when `LANGGRAPH_INTERRUPT=true`.

## 8. Improvement plan
1. Implement a more robust evaluation system (LLM-as-judge with detailed evaluation rubric).
2. Build a full web/Streamlit UI for the HITL approval system.
3. Add OpenTelemetry or LangSmith tracing for visual execution paths.
