"""build_registry() is the single place tools are bound to settings. agent.py imports only this."""

from __future__ import annotations

from functools import partial

from pydantic import BaseModel, Field

from ..config import Settings
from ..retrieval import Retriever
from . import actions, faults, knowledge
from .base import ToolError, ToolRegistry, ToolSpec


class ListFindingsArgs(BaseModel):
    severity: str | None = Field(
        default=None,
        description=(
            "Raw CVSS band: critical|high|medium|low|needs_review. This is NOT the "
            "policy-adjusted severity - apply the severity rubric yourself."
        ),
    )
    asset_id: str | None = Field(default=None, description="Asset id, e.g. A-001")
    status: str | None = Field(
        default=None, description="open|in_progress|closed. Default: every non-closed finding."
    )
    limit: int = Field(default=25, ge=1, le=100)


class GetFindingArgs(BaseModel):
    finding_id: str = Field(description="Finding id, e.g. F-004")


class GetAssetArgs(BaseModel):
    asset_id: str = Field(description="Asset id, e.g. A-003")


class SearchPolicyArgs(BaseModel):
    query: str = Field(
        description="Natural-language question about the severity rubric, SLA or escalation policy"
    )
    k: int = Field(default=4, ge=1, le=8)


class CreateTicketArgs(BaseModel):
    finding_id: str = Field(description="Finding the ticket is for, e.g. F-012")
    owner: str = Field(description="Asset owner, taken from get_asset or the findings row")
    severity: str = Field(description="Policy-adjusted severity: critical|high|medium|low")
    due_date: str = Field(description="ISO date YYYY-MM-DD, derived from the SLA policy")
    summary: str = Field(description="One line describing the remediation required")


class ApprovalArgs(BaseModel):
    question: str = Field(description="What you are asking the human to approve, in one sentence")
    finding_id: str = Field(default="", description="Finding the approval concerns")


class EscalateArgs(BaseModel):
    finding_id: str = Field(description="Finding to escalate, e.g. F-009")
    reason: str = Field(description="Why escalation is warranted, citing the policy")
    approver: str = Field(description="Approver identity returned by request_human_approval")
    approval_ref: str = Field(description="approval_ref returned by request_human_approval")


def build_registry(settings: Settings, retriever: Retriever) -> ToolRegistry:
    reg = ToolRegistry()
    injector = faults.FaultInjector(settings.inject_fault)

    def guarded(name: str, fn):
        """Wrap a data/action tool so an injected fault surfaces as a normal tool failure."""

        def wrapper(**kwargs):
            injector.before_call(name)
            return fn(**kwargs)

        return wrapper

    reg.register(
        ToolSpec(
            name="search_policy",
            description=(
                "Search the written severity rubric, remediation SLA, escalation and change "
                "management policies. Use this before deciding any severity or deadline."
            ),
            args_model=SearchPolicyArgs,
            fn=lambda query, k=4: retriever.search(query, k=k),
        )
    )
    reg.register(
        ToolSpec(
            name="list_findings",
            description=(
                "List findings from the register, optionally filtered by CVSS band or asset."
            ),
            args_model=ListFindingsArgs,
            fn=guarded("list_findings", partial(knowledge.list_findings, settings.db_path)),
        )
    )
    reg.register(
        ToolSpec(
            name="get_finding",
            description="Full detail for one finding, including its asset context.",
            args_model=GetFindingArgs,
            fn=guarded("get_finding", partial(knowledge.get_finding, settings.db_path)),
        )
    )
    reg.register(
        ToolSpec(
            name="get_asset",
            description="Ownership, business criticality and environment for one asset.",
            args_model=GetAssetArgs,
            fn=guarded("get_asset", partial(knowledge.get_asset, settings.db_path)),
        )
    )
    reg.register(
        ToolSpec(
            name="create_ticket",
            description="Open a remediation ticket for a finding.",
            args_model=CreateTicketArgs,
            fn=guarded("create_ticket", partial(actions.create_ticket, settings.tickets_path)),
            writes=True,
        )
    )
    reg.register(
        ToolSpec(
            name="request_human_approval",
            description=(
                "Ask the human operator to approve a consequential action. Always call this before "
                "escalate - it is the only source of a valid approval_ref."
            ),
            args_model=ApprovalArgs,
            fn=guarded(
                "request_human_approval",
                partial(actions.request_human_approval, auto_approve=settings.auto_approve),
            ),
        )
    )
    reg.register(
        ToolSpec(
            name="escalate",
            description=(
                "Escalate a breached finding to the security operations lead. Irreversible: writes "
                "an auditable record."
            ),
            args_model=EscalateArgs,
            fn=guarded("escalate", partial(actions.escalate, settings.escalations_path)),
            writes=True,
            side_effect=True,
        )
    )
    return reg


__all__ = ["ToolError", "ToolRegistry", "ToolSpec", "build_registry"]
