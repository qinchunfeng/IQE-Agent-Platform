"""预置流水线模板。

逐字对齐文档 4.2 的 IQE 流水线组合示例(字段与顺序不变)。
文档 4.2 与场景 4 对“默认编排器”存在矛盾(C1):这里保留 4.2 的
airflow_orchestrator,运行时按文档 7.4 自动降级到内置编排器。
"""

from __future__ import annotations

from . import db
from .services.pipeline_service import DEFAULT_PIPELINE_ID

DEFAULT_PIPELINE: dict = {
    "pipeline_id": DEFAULT_PIPELINE_ID,
    "orchestrator": "airflow_orchestrator",
    "stages": [
        {
            "agent": "monitor_agent",
            "input_source": "jenkins_webhook",
            "llm_provider": "qoder_cn",
            "knowledge_base": None,
        },
        {
            "agent": "triage_agent",
            "llm_provider": "qoder_cn",
            "knowledge_base": "memory_vector_kb",
        },
        {
            "agent": "reproduction_agent",
            "tool": "jarvis_mock",
            "llm_provider": "qoder_cn",
        },
        {
            "agent": "ticket_agent",
            "tool": "jira_mock",
            "llm_provider": "qoder_cn",
        },
        {
            "agent": "reviewer_agent",
            "llm_provider": "qoder_cn",
            "knowledge_base": "memory_vector_kb",
            "human_gate": True,
        },
        {
            "agent": "reporting_agent",
            "llm_provider": "qoder_cn",
        },
    ],
}


def seed_default_pipeline() -> None:
    if db.get_pipeline(DEFAULT_PIPELINE_ID) is None:
        db.save_pipeline(DEFAULT_PIPELINE)
