[model tier policy — COMPACTION BOUNDARY ({model})] The conversation was just compacted. What the summary says happened
is not what you verified: provenance — who did what, who approved what — is exactly what a summary compresses away, and
a missing actor read back as "I" is how a coordinator manufactures its own authorization. Until re-verified, every
actor, approval, and precedent in the summary is unverified. Reload state from the tracker only
(`{plans}/<slug>.tracker.md` — its `last` and `auth` columns are the ledger); do not perform, and do not dispatch, any
irreversible action — a merge, a push to a shared branch, a close, a delete — on the strength of the summary; re-verify
the current ref and the authorization state first, one cheap call each. Before the next dispatch, have "{steward}"
reconcile the tracker's rows against their handles.
