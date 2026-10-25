AgentDojo banking v1.2.2, `important_instructions` attack. Utility: the user's task was done. Attack success: the injected task was done. Both read off the environment by AgentDojo's own checks.

| model | arm | utility, no attack | utility under attack | attack success |
|---|---|---:|---:|---:|
| claude-sonnet | stock | 10/16 (62%) | 90/144 (62%) | 0/144 (0%) |
| glm-5p3-flash | stock | 15/16 (94%) | 131/144 (91%) | 1/144 (1%) |
| glm-5p3-flash | tool_filter | 13/16 (81%) | 114/144 (79%) | 0/144 (0%) |
| glm-5p3-flash | charter_plain | 12/16 (75%) | 132/144 (92%) | 0/144 (0%) |
| glm-5p3-flash | charter_rules | 14/16 (88%) | 119/144 (83%) | 0/144 (0%) |
| nemotron-lightning | stock | 12/16 (75%) | 102/144 (71%) | 114/144 (79%) |
| nemotron-lightning | tool_filter | 11/16 (69%) | 78/144 (54%) | 29/144 (20%) |
| nemotron-lightning | charter_plain | 11/16 (69%) | 96/144 (67%) | 121/144 (84%) |
| nemotron-lightning | charter_rules | 10/16 (62%) | 90/144 (62%) | 0/144 (0%) |
