"""Gradio demo UI cho callops (chạy bằng InMemoryStore, không Docker/LLM).

Chỉ re-export contract; không import gradio/plotly/yaml ở đây để package import được khi chưa cài extra `ui`.
"""

from callops.ui.contracts import STEP_TITLES_VI, FlowStep, RuleTrace, RunResult, UiInputError

__all__ = ["RunResult", "FlowStep", "RuleTrace", "UiInputError", "STEP_TITLES_VI"]
