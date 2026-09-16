"""
The two tool surfaces a scenario can be run through.

An *arm* is the only thing that differs between two runs of the same scenario:
same model, same prompt, same credentials, same endpoints, same limits — and a
different set of tools between the model and the wire.

- :mod:`charter_arm` hands the model the pack's Charter tools, projected into
  Inspect ``ToolDef`` objects straight from ``Tool.to_json_schema()``.
- :mod:`raw_arm` hands the model one ``<provider>_api`` tool per provider that
  sends whatever it is given — the API glue people actually write first.

Both write to the same :class:`~charter_harness.arms.ledger.Ledger`, so the
report can compare them on tool calls, errors, and bytes fed to the model.
"""

from charter_harness.arms.base import ARMS, Arm, arm_by_name

__all__ = ["ARMS", "Arm", "arm_by_name"]
