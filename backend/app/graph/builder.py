"""Assemble the LangGraph tutor graph (architecture 3.2).

Wires nodes with conditional edges and loops:
  * Intent Router → goal / question / code / clarify
  * goal → skill path → task selector → respond
  * question → retrieve → generate → (self-execute loop) → respond
  * code → validate → passed (progress → adapt → select task) / failed
    (classify → remediate → select task) → respond

Uses a PostgresSaver checkpointer for durable, resumable sessions and
human-in-the-loop interrupts.
"""
from __future__ import annotations

import logging
from contextlib import ExitStack

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from app.config import settings
from app.graph.state import TutorState
from app.graph.nodes.adaptivity import adaptivity_engine
from app.graph.nodes.answer_generator import answer_generator
from app.graph.nodes.code_validator import code_validator
from app.graph.nodes.error_classifier import error_classifier
from app.graph.nodes.goal_planner import goal_planner
from app.graph.nodes.misc import clarify, respond
from app.graph.nodes.progress import progress_updater
from app.graph.nodes.remediation import remediation_planner
from app.graph.nodes.retriever import rag_retriever
from app.graph.nodes.router import intent_router
from app.graph.nodes.self_execution import self_execution
from app.graph.nodes.skill_path import skill_path_builder
from app.graph.nodes.task_selector import task_selector
from app.graph.nodes.topic_guard import topic_guard
from app.graph.nodes.web_search import web_search_node

logger = logging.getLogger(__name__)


# --- Conditional routing functions -----------------------------------------

def route_topic_guard(state) -> str:
    """Off-topic messages skip routing/RAG/execution and go straight to respond."""
    return "respond" if state.get("off_topic") else "intent_router"


def route_intent(state) -> str:
    return {
        "goal": "goal_planner",
        "question": "rag_retriever",
        "code": "code_validator",
        "clarify": "clarify",
    }.get(state.get("intent", "question"), "rag_retriever")


def route_after_generate(state) -> str:
    return "self_execution" if state.get("next_action") == "self_execute" else "respond"


def route_self_execution(state) -> str:
    return "self_execution" if state.get("next_action") == "self_execute" else "respond"


def route_validation(state) -> str:
    return "progress_updater" if state.get("next_action") == "passed" else "error_classifier"


def route_adaptivity(state) -> str:
    return "task_selector" if state.get("next_action") == "select_task" else "respond"


def build_graph(checkpointer):
    # Use the typed schema (TutorState) rather than a bare ``dict``. With a bare
    # ``dict`` schema LangGraph has no channel definitions, so partial updates
    # returned by nodes are not reliably merged into the shared state (the final
    # state ended up containing only the original input keys). TutorState declares
    # each field as a channel (and ``messages`` as an add_messages reducer), so
    # node return dicts merge correctly turn-to-turn.
    g = StateGraph(TutorState)

    # Register nodes
    g.add_node("intent_router", intent_router)
    g.add_node("goal_planner", goal_planner)
    g.add_node("skill_path_builder", skill_path_builder)
    g.add_node("task_selector", task_selector)
    g.add_node("rag_retriever", rag_retriever)
    g.add_node("answer_generator", answer_generator)
    g.add_node("self_execution", self_execution)
    g.add_node("code_validator", code_validator)
    g.add_node("error_classifier", error_classifier)
    g.add_node("web_search_node", web_search_node)
    g.add_node("remediation_planner", remediation_planner)
    g.add_node("progress_updater", progress_updater)
    g.add_node("adaptivity_engine", adaptivity_engine)
    g.add_node("clarify", clarify)
    g.add_node("respond", respond)
    g.add_node("topic_guard", topic_guard)

    # Entry → topic guard → router (or straight to respond when off-topic)
    g.add_edge(START, "topic_guard")
    g.add_conditional_edges(
        "topic_guard",
        route_topic_guard,
        {"intent_router": "intent_router", "respond": "respond"},
    )
    g.add_conditional_edges(
        "intent_router",
        route_intent,
        {
            "goal_planner": "goal_planner",
            "rag_retriever": "rag_retriever",
            "code_validator": "code_validator",
            "clarify": "clarify",
        },
    )

    # Goal branch
    g.add_edge("goal_planner", "skill_path_builder")
    g.add_edge("skill_path_builder", "task_selector")
    g.add_edge("task_selector", "respond")

    # Question branch (with self-execution loop)
    g.add_edge("rag_retriever", "answer_generator")
    g.add_conditional_edges(
        "answer_generator",
        route_after_generate,
        {"self_execution": "self_execution", "respond": "respond"},
    )
    g.add_conditional_edges(
        "self_execution",
        route_self_execution,
        {"self_execution": "self_execution", "respond": "respond"},
    )

    # Code branch
    g.add_conditional_edges(
        "code_validator",
        route_validation,
        {"progress_updater": "progress_updater", "error_classifier": "error_classifier"},
    )
    g.add_edge("progress_updater", "adaptivity_engine")
    g.add_conditional_edges(
        "adaptivity_engine",
        route_adaptivity,
        {"task_selector": "task_selector", "respond": "respond"},
    )
    # Failure path: classify → fetch remediation links/excerpt (web_search) →
    # plan remediation. ``web_search_node`` is strictly fail-open and always
    # routes onward to ``remediation_planner`` (Group C, plan §4.3).
    g.add_edge("error_classifier", "web_search_node")
    g.add_edge("web_search_node", "remediation_planner")
    g.add_edge("remediation_planner", "task_selector")

    # Terminal nodes
    g.add_edge("clarify", "respond")
    g.add_edge("respond", END)

    return g.compile(checkpointer=checkpointer)


# --- Singleton compiled graph with Postgres checkpointer --------------------

_graph = None
_stack: ExitStack | None = None


def get_graph():
    global _graph, _stack
    if _graph is not None:
        return _graph

    try:
        from langgraph.checkpoint.postgres import PostgresSaver

        _stack = ExitStack()
        cm = PostgresSaver.from_conn_string(settings.psycopg_url)
        checkpointer = _stack.enter_context(cm)
        checkpointer.setup()
        logger.info("Using PostgresSaver checkpointer")
    except Exception as exc:  # noqa: BLE001
        logger.warning("PostgresSaver unavailable (%s); falling back to MemorySaver", exc)
        checkpointer = MemorySaver()

    _graph = build_graph(checkpointer)
    return _graph
