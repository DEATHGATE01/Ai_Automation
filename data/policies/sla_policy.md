# Remediation SLA Policy

## Remediation windows
Critical findings must be remediated within 7 days of detection. High findings within 30 days.
Medium findings within 90 days. Low findings within 180 days.
Findings marked `needs_review` are frozen: they are not subject to an SLA until a score is assigned.

## Breach definition
A finding is in breach when days_open exceeds the remediation window for its severity AND its
status is not closed.

## Due-soon definition
A finding is due soon when the remaining days before breach are 7 or fewer.
