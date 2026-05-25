"""Gatekeeper — danger-level gate + trusted-routine + burst + audit + allow-rules."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from yuki.safety.allow_rules import AllowRules
from yuki.safety.audit import append_action_audit
from yuki.safety.burst import BurstMode
from yuki.safety.confirmer import Confirmer
from yuki.safety.decision import Decision, Reason
from yuki.safety.trusted import TrustedRoutineRegistry
from yuki.tools.native.registry import DangerLevel, ToolSpec


def _preview(spec: ToolSpec, args: dict[str, Any]) -> str:
    return f"{spec.name}({', '.join(f'{k}={v!r}' for k, v in args.items())})"


class Gatekeeper:
    def __init__(
        self,
        confirmer: Confirmer,
        trusted: TrustedRoutineRegistry,
        burst: BurstMode,
        allow_rules: AllowRules | None = None,
    ) -> None:
        self._confirmer = confirmer
        self._trusted = trusted
        self._burst = burst
        self._allow_rules = allow_rules or AllowRules(session_id="default")

    async def gate(self, spec: ToolSpec, args: dict[str, Any]) -> Decision:
        # 1. Tool's own check_permissions takes priority.
        if spec.check_permissions is not None:
            verdict = spec.check_permissions(args, None)
            if verdict == "deny":
                return Decision.deny(reason=Reason.SAFETY_FORBIDDEN)
            if verdict == "allow":
                return Decision.approve(payload=dict(args), reason=Reason.AUTO_READ_ONLY)
            # "ask" → fall through

        # 2. READ_ONLY auto-approves.
        if spec.danger == DangerLevel.READ_ONLY:
            return Decision.approve(payload=dict(args), reason=Reason.AUTO_READ_ONLY)

        # 3. Allow-rules (session/project/user).
        if self._allow_rules.is_allowed(tool_name=spec.name, args=args):
            return Decision.approve(payload=dict(args), reason=Reason.USER)

        # 4. REVERSIBLE escape valves.
        if spec.danger == DangerLevel.REVERSIBLE:
            if self._trusted.is_active():
                return Decision.approve(
                    payload=dict(args), reason=Reason.AUTO_TRUSTED_ROUTINE
                )
            if self._burst.is_active():
                return Decision.approve(
                    payload=dict(args), reason=Reason.AUTO_BURST_MODE
                )

        # 5. EXTERNAL + DESTRUCTIVE always ask; REVERSIBLE asks if no escape valve.
        return await self._confirmer.ask(
            tool_name=spec.name,
            args=dict(args),
            danger=spec.danger.value,
            preview=_preview(spec, args),
        )

    def record_executed(
        self, spec: ToolSpec, args: dict[str, Any], decision: Decision
    ) -> None:
        if not decision.approved:
            return
        append_action_audit(
            tool_name=spec.name,
            args=args,
            danger=spec.danger.value,
            reason=decision.reason.value,
            ts=datetime.now(UTC),
        )
