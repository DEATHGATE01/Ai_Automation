# Severity Rubric

## CVSS bands
CVSS 9.0-10.0 is critical. CVSS 7.0-8.9 is high. CVSS 4.0-6.9 is medium. CVSS 0.1-3.9 is low.

## Business criticality adjustment
When an asset's business criticality is `critical` or `high`, raise the CVSS band by one level.
When an asset's business criticality is `low`, lower the band by one level. Never adjust below low
or above critical.

## Unscored findings
A finding with no CVSS score must not be assigned a severity from the CVSS bands. Treat it as
`needs_review` and state explicitly that the score is missing.
