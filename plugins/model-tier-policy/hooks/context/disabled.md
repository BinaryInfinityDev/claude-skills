[model tier policy — DISABLED for this session. Orchestrator mode expects the orchestrator role's model
({orchestrator_model}), but this session runs on {model}, a higher tier: the policy stands down rather than coordinate
on a costlier tier than configured — no denials, no delegation reminders, and nothing is enforcing the tier split. To
restore it: open the session on {orchestrator_model}, raise `models.orchestrator` in `.claude/model-tier-policy.json`,
or set `orchestrator_mode` false to run the premium posture instead.]
