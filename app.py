import streamlit as st
import os
import uuid
from dotenv import load_dotenv

# Ensure environment variables are loaded
load_dotenv()

# Force LangGraph HITL interrupt mode
os.environ["LANGGRAPH_INTERRUPT"] = "true"

from langgraph_agent_lab.graph import build_graph
from langgraph_agent_lab.persistence import build_checkpointer
from langgraph_agent_lab.state import initial_state, Scenario, Route
from langgraph.types import Command

# Set up page styling
st.set_page_config(
    page_title="Agent Portal",
    page_icon="🛡️",
    layout="wide"
)

# Initialize Global session state for multi-thread tracking
if "threads" not in st.session_state:
    st.session_state.threads = {}
if "active_thread_id" not in st.session_state:
    st.session_state.active_thread_id = f"chat-{uuid.uuid4().hex[:6]}"

# Cache graph builder
@st.cache_resource
def get_graph():
    # Use memory checkpointer for dynamic UI chat session
    checkpointer = build_checkpointer("memory")
    return build_graph(checkpointer=checkpointer)

graph = get_graph()

# Helper to ensure the active thread exists in session state
def get_active_thread_data():
    t_id = st.session_state.active_thread_id
    if t_id not in st.session_state.threads:
        st.session_state.threads[t_id] = {
            "messages": [],
            "events": [],
            "pending_approval": None
        }
    return st.session_state.threads[t_id]

# ----------------------------------------------------
# PAGE 1: Chat interface
# ----------------------------------------------------
def chat_page():
    st.title("🤖 Customer Support Workspace")
    st.write("Submit customer support tickets. If a sensitive or risky action is requested, it will pause and await administrator approval.")

    thread_data = get_active_thread_data()
    t_id = st.session_state.active_thread_id
    config = {"configurable": {"thread_id": t_id}}

    # Display thread history
    for message in thread_data["messages"]:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # If there is a pending approval for the current thread, display a notice pointing to the approval tab
    if thread_data["pending_approval"]:
        st.warning(f"⚠️ **Action Pending Administrator Review**: The request *'{thread_data['pending_approval']['proposed_action']}'* requires approval. Please navigate to the **Sensitive Action Approvals** page to authorize it.")

    # Chat Input Block
    else:
        if prompt := st.chat_input("Enter ticket details (e.g. refund, delete account, reset password)..."):
            # Display user query
            thread_data["messages"].append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)

            with st.spinner("Processing ticket..."):
                scenario = Scenario(id="streamlit-live", query=prompt, expected_route=Route.SIMPLE)
                state = initial_state(scenario)
                state["thread_id"] = t_id

                # Run graph
                result = graph.invoke(state, config=config)

                # Check if it was interrupted
                state_snapshot = graph.get_state(config)
                if state_snapshot.next and "approval" in state_snapshot.next:
                    for task in state_snapshot.tasks:
                        if task.interrupts:
                            thread_data["pending_approval"] = {
                                "proposed_action": task.interrupts[0].value.get("proposed_action", "Sensitive Action"),
                                "question": task.interrupts[0].value.get("question", "Verification needed."),
                                "task_id": task.id
                            }
                            break
                
                # Log execution events and replies
                thread_data["events"] = result.get("events", [])
                if result.get("pending_question"):
                    thread_data["messages"].append({"role": "assistant", "content": result["pending_question"]})
                elif result.get("final_answer"):
                    thread_data["messages"].append({"role": "assistant", "content": result["final_answer"]})
                
                st.rerun()

    # Sidebar Controls (Current Thread Context)
    with st.sidebar:
        st.subheader("🧵 Active Session")
        st.write(f"Thread: `{t_id}`")
        
        if st.button("🆕 Start New Ticket"):
            st.session_state.active_thread_id = f"chat-{uuid.uuid4().hex[:6]}"
            st.rerun()

        # Display history dropdown to switch sessions
        if len(st.session_state.threads) > 1:
            st.markdown("---")
            st.subheader("Switch Active Ticket")
            selected_thread = st.selectbox(
                "Select thread ID", 
                options=list(st.session_state.threads.keys()),
                index=list(st.session_state.threads.keys()).index(t_id)
            )
            if selected_thread != t_id:
                st.session_state.active_thread_id = selected_thread
                st.rerun()

        # Visual Trace Logs
        if thread_data["events"]:
            st.markdown("---")
            st.subheader("🔍 Active Trace History")
            for idx, event in enumerate(thread_data["events"]):
                node_name = event.get("node", "unknown").upper()
                st.markdown(f"**{idx + 1}. [{node_name}]**  \n*{event.get('message')}*")

# ----------------------------------------------------
# PAGE 2: Admin Approval Panel
# ----------------------------------------------------
def approval_page():
    st.title("🔒 Sensitive Action Approvals Dashboard")
    st.write("Review and decide on active human-in-the-loop requests initiated by customer support threads.")

    # Find all threads that are currently pending approval
    pending_threads = {
        t_id: data for t_id, data in st.session_state.threads.items() 
        if data.get("pending_approval") is not None
    }

    if not pending_threads:
        st.success("✅ **All Clear**: No sensitive operations require administrator review at this time.")
        return

    # Render a card for each pending request
    for t_id, data in pending_threads.items():
        approval_info = data["pending_approval"]
        config = {"configurable": {"thread_id": t_id}}

        with st.container(border=True):
            st.subheader(f"Request on Thread ID: `{t_id}`")
            st.write(f"**Proposed Operation:** :orange[{approval_info['proposed_action']}]")
            st.info(f"**Trigger Reason:** {approval_info['question']}")
            
            # Let the admin submit comments
            comment = st.text_input("Reviewer Feedback / Comments", value="Action Approved", key=f"comm-{t_id}")
            
            col1, col2 = st.columns(2)
            with col1:
                if st.button("✅ Approve Action", key=f"app-{t_id}", type="primary"):
                    with st.spinner("Authorizing and resuming workflow..."):
                        result = graph.invoke(
                            Command(resume={
                                "approved": True,
                                "reviewer": "Admin Console",
                                "comment": comment
                            }),
                            config=config
                        )
                        # Clear approval state and append final response
                        data["pending_approval"] = None
                        data["events"] = result.get("events", [])
                        if result.get("final_answer"):
                            data["messages"].append({"role": "assistant", "content": result["final_answer"]})
                        elif result.get("pending_question"):
                            data["messages"].append({"role": "assistant", "content": result["pending_question"]})
                        st.success("Approved successfully!")
                        st.rerun()

            with col2:
                if st.button("❌ Reject & Clarify", key=f"rej-{t_id}", type="secondary"):
                    with st.spinner("Rejecting and routing to clarification..."):
                        result = graph.invoke(
                            Command(resume={
                                "approved": False,
                                "reviewer": "Admin Console",
                                "comment": comment
                            }),
                            config=config
                        )
                        # Clear approval state and append clarification response
                        data["pending_approval"] = None
                        data["events"] = result.get("events", [])
                        if result.get("final_answer"):
                            data["messages"].append({"role": "assistant", "content": result["final_answer"]})
                        elif result.get("pending_question"):
                            data["messages"].append({"role": "assistant", "content": result["pending_question"]})
                        st.warning("Action rejected and routed to customer.")
                        st.rerun()

# Define Navigation
pg = st.navigation([
    st.Page(chat_page, title="Customer Chat", icon="💬"),
    st.Page(approval_page, title="Sensitive Approvals", icon="🔒")
])
pg.run()
