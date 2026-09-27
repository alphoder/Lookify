"""Laya (open-source, local Jev alternative) smoke test. First run downloads ~808 MB.

  .venv/bin/python laya_check.py
"""
import laya

agent = laya.load("convaiinnovations/laya")

# same question the old Jev test asked (Jev "boolean" == Laya "noul")
refund = agent.predict("I was charged twice. Please refund the duplicate.", {
    "requestsRefund": {"type": "noul", "instructions": "Is the customer requesting money back?"},
})
p = refund["answers"]["requestsRefund"]["noul"]
print("requestsRefund:", p)
assert p > 0.5, "expected a refund request"

# the kind of decision the kitchen monitor would hand it
state = {"worker": "W02", "window_s": 60, "head_cover_missing_s": 42, "gloves_missing_s": 60,
         "phone_s": 0, "idle_s": 12, "station": "packing"}
kitchen = agent.predict(state, {
    "severity": {"type": "choice", "instructions": "How serious is this worker's hygiene record in the last minute?",
                 "criteria": {"ok": "compliant or trivial lapse", "warn": "a short lapse worth a reminder",
                              "escalate": "sustained violation, a manager should step in"}},
    "alert_manager": {"type": "noul", "instructions": "Should the shift manager be alerted right now?"},
})
print("severity:", kitchen["answers"]["severity"]["choice"])
print("alert_manager:", kitchen["answers"]["alert_manager"]["noul"])
