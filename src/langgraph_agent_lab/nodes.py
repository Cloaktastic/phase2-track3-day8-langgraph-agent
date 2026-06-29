"""Node functions for the LangGraph workflow.

Each function receives AgentState and returns a partial state update dict.
Do NOT mutate input state — return new values only.

LLM REQUIREMENT:
- classify_node MUST use a real LLM call (structured output for intent classification)
- answer_node MUST use a real LLM call (grounded response generation)
- evaluate_node SHOULD use LLM-as-judge (bonus points; heuristic acceptable for base score)
"""

from __future__ import annotations

from .state import AgentState, make_event


# ─── EXAMPLE: working node (provided for reference) ──────────────────
def intake_node(state: AgentState) -> dict:
    """Normalize raw query. This node is provided as a working example."""
    query = state.get("query", "").strip()
    return {
        "query": query,
        "messages": [f"intake:{query[:40]}"],
        "events": [make_event("intake", "completed", "query normalized")],
    }


import os
from pydantic import BaseModel, Field
from .llm import get_llm

class Classification(BaseModel):
    route: str = Field(description="The classified intent route. One of: simple, tool, missing_info, risky, error.")
    risk_level: str = Field(description="The risk level of the query. Set to 'high' for risky routes, and 'low' otherwise.")

class Evaluation(BaseModel):
    is_successful: bool = Field(description="Whether the tool result represents a successful run without errors/failures.")
    reason: str = Field(description="Brief explanation of the evaluation decision.")


# ─── TODO(student): implement ALL nodes below ────────────────────────


def classify_node(state: AgentState) -> dict:
    """Classify the query into a route using an LLM.

    *** MUST use a real LLM call — keyword-only heuristics will lose points. ***

    Use .with_structured_output() or equivalent to get reliable enum classification.
    The LLM should classify into one of: simple, tool, missing_info, risky, error.
    """
    query = state.get("query", "")
    llm = get_llm()
    structured_llm = llm.with_structured_output(Classification)

    prompt = f"""You are a customer support ticket router. Classify the user query into one of these routes:
- risky: Actions with side effects like refunds, account deletions, cancellations, or sending custom emails.
- tool: Information lookups like order status, shipment tracking, or searching details.
- missing_info: Vague or incomplete queries that lack actionable context or specific details to help.
- error: System or application failures (e.g. timeouts, crashes, server unavailable).
- simple: General questions that can be answered immediately with simple advice without using tools or performing actions.

Priority ordering: risky > tool > missing_info > error > simple. If a query could match multiple, pick the one with highest priority.

Query: "{query}"
"""
    result = structured_llm.invoke(prompt)
    route_val = result.route
    risk_val = result.risk_level

    # Ensure validity
    valid_routes = {"simple", "tool", "missing_info", "risky", "error"}
    if route_val not in valid_routes:
        route_val = "simple"

    return {
        "route": route_val,
        "risk_level": risk_val,
        "events": [make_event("classify", "completed", f"classified query as {route_val} with risk {risk_val}")],
    }


def tool_node(state: AgentState) -> dict:
    """Execute a mock tool call.

    Simulate transient failures for error-route scenarios to test retry loops.

    Requirements:
    - Read current attempt count from state
    - If route is "error" and attempt < 2: return error result (string containing "ERROR")
    - Otherwise: return a mock success result string
    - Append result to tool_results list
    """
    attempt = state.get("attempt", 0)
    route = state.get("route")
    
    if route == "error" and attempt < 2:
        result = f"Tool failed with ERROR: connection timeout (attempt {attempt})"
    else:
        result = "Tool execution succeeded. Order status is: SHIPPED. Details: Order ID 12345."

    return {
        "tool_results": [result],
        "events": [make_event("tool", "completed", f"executed tool, success: {'ERROR' not in result}")],
    }


def evaluate_node(state: AgentState) -> dict:
    """Evaluate tool results — the retry-loop gate.

    Check whether the latest tool result is satisfactory or needs retry.

    SHOULD use LLM-as-judge for bonus points. Heuristic (e.g., check for "ERROR" substring)
    is acceptable for base score.
    """
    tool_results = state.get("tool_results", [])
    latest_result = tool_results[-1] if tool_results else ""

    # Establish robust fallback default
    if "ERROR" in latest_result or "failed" in latest_result.lower():
        evaluation_result = "needs_retry"
    else:
        evaluation_result = "success"

    # Apply LLM as judge
    try:
        llm = get_llm()
        structured_llm = llm.with_structured_output(Evaluation)
        prompt = f"""Evaluate the following tool execution result. Determine if it was successful or if it contains an error/failure that requires a retry.
Tool Result: "{latest_result}"
"""
        eval_out = structured_llm.invoke(prompt)
        evaluation_result = "success" if eval_out.is_successful else "needs_retry"
    except Exception:
        pass

    return {
        "evaluation_result": evaluation_result,
        "events": [make_event("evaluate", "completed", f"evaluated tool result as {evaluation_result}")],
    }


def answer_node(state: AgentState) -> dict:
    """Generate a final response using an LLM.

    *** MUST use a real LLM call — hardcoded strings will lose points. ***

    The LLM should generate a helpful response grounded in available context:
    - tool_results (if any)
    - approval decision (if risky route)
    - original query
    """
    query = state.get("query", "")
    tool_results = state.get("tool_results", [])
    approval = state.get("approval")

    context = f"User Query: {query}\n"
    if tool_results:
        context += f"Tool Results: {tool_results}\n"
    if approval:
        context += f"Approval Decision: {approval}\n"

    prompt = f"""You are a helpful customer support assistant. Generate a polite and helpful final answer for the user query, grounded in the context provided.

{context}

If tools returned information, integrate it cleanly into your response without showing internal technical details or error traceback to the user.
"""
    llm = get_llm()
    response = llm.invoke(prompt)

    return {
        "final_answer": response.content,
        "events": [make_event("answer", "completed", "generated grounded final answer")],
    }


def ask_clarification_node(state: AgentState) -> dict:
    """Ask for missing information instead of hallucinating.

    Generate a specific clarification question based on the vague/incomplete query.
    """
    query = state.get("query", "")
    prompt = f"""The user query is too vague or incomplete for us to proceed:
Query: "{query}"

Generate a polite clarification question to ask the customer to obtain the missing details.
"""
    llm = get_llm()
    response = llm.invoke(prompt)
    question = response.content

    return {
        "pending_question": question,
        "final_answer": question,
        "events": [make_event("clarify", "completed", "generated clarification question")],
    }


def risky_action_node(state: AgentState) -> dict:
    """Prepare a risky action for human approval.

    Describe the proposed action and why it requires approval.
    """
    query = state.get("query", "")
    prompt = f"""Describe the proposed action and why it requires human approval for this risky user query.
Query: "{query}"

Format: A clear, single-sentence summary of the action and risk.
"""
    llm = get_llm()
    response = llm.invoke(prompt)
    proposed_action = response.content

    return {
        "proposed_action": proposed_action,
        "events": [make_event("risky_action", "completed", f"proposed action: {proposed_action[:50]}")],
    }


def approval_node(state: AgentState) -> dict:
    """Human-in-the-loop approval step.

    Default behavior: mock approval (approved=True) so tests and CI run offline.
    Extension: if env LANGGRAPH_INTERRUPT=true, use langgraph.types.interrupt() for real HITL.
    """
    if os.getenv("LANGGRAPH_INTERRUPT") == "true":
        from langgraph.types import interrupt
        action = state.get("proposed_action", "risky action")
        decision = interrupt({
            "question": f"Do you approve the following action? '{action}'",
            "proposed_action": action
        })
        if isinstance(decision, dict) and "approved" in decision:
            approval_dict = {
                "approved": bool(decision.get("approved")),
                "reviewer": str(decision.get("reviewer", "human-reviewer")),
                "comment": str(decision.get("comment", "")),
            }
        else:
            approval_dict = {
                "approved": False,
                "reviewer": "human-reviewer",
                "comment": "No valid decision provided",
            }
    else:
        approval_dict = {
            "approved": True,
            "reviewer": "mock-reviewer",
            "comment": "auto-approved",
        }

    return {
        "approval": approval_dict,
        "events": [make_event("approval", "completed", f"action approved: {approval_dict['approved']}")],
    }


def retry_or_fallback_node(state: AgentState) -> dict:
    """Record a retry attempt.

    Increment the attempt counter and log the transient failure.

    Requirements:
    - Read current attempt from state, increment by 1
    - Add an error message to errors list
    - Return updated attempt count
    """
    attempt = state.get("attempt", 0) + 1
    error_msg = f"Attempt {attempt} failed: Simulating transient error or service timeout."
    return {
        "attempt": attempt,
        "errors": [error_msg],
        "events": [make_event("retry", "completed", f"incremented attempt to {attempt}")],
    }


def dead_letter_node(state: AgentState) -> dict:
    """Handle unresolvable failures after max retries exceeded.

    This is the third layer: retry → fallback → dead letter.
    Log the failure and set a final_answer explaining that the request could not be completed.
    """
    errors_summary = "; ".join(state.get("errors", []))
    final_answer = f"We apologize, but your request could not be completed after multiple attempts. Technical details: {errors_summary}"
    return {
        "final_answer": final_answer,
        "events": [make_event("dead_letter", "completed", "max retries exceeded, escalated to dead letter")],
    }


def finalize_node(state: AgentState) -> dict:
    """Emit a final audit event. All routes must pass through here before END.
    """
    return {
        "events": [make_event("finalize", "completed", "workflow finished")],
    }
