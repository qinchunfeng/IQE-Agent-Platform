"""预置流水线模板。

逐字对齐文档 4.2 的 IQE 流水线组合示例(Agent 字段与顺序不变)。
【已确认 Q24】Airflow 改为输入源插件,默认编排器统一为内置 memory_orchestrator;
默认输入源保留 Mock Jenkins,Airflow/外部日志文件由画布按需添加。
"""

from __future__ import annotations

from . import db
from .services.pipeline_service import DEFAULT_PIPELINE_ID, normalize_definition

DEFAULT_PIPELINE: dict = {
    "pipeline_id": DEFAULT_PIPELINE_ID,
    "orchestrator": "memory_orchestrator",
    "sources": [
        {
            "source_id": "mock_jenkins",
            "plugin_id": "mock_jenkins",
            "label": "Jenkins / Mock Jenkins",
            "enabled": True,
        }
    ],
    "stages": [
        {
            "agent": "monitor_agent",
            "input_source": "mock_jenkins",
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
    record = db.get_pipeline(DEFAULT_PIPELINE_ID)
    if record is None:
        db.save_pipeline(DEFAULT_PIPELINE)
        return
    # 旧 Demo 数据库迁移:airflow_orchestrator → memory_orchestrator,并补齐输入源节点。
    normalized = normalize_definition(record["definition"])
    if normalized != record["definition"]:
        db.save_pipeline(normalized)
