"""Inference-owned package boundary for target-result, prompt, provider, and evidence contracts.

This package owns the strict complete-target-result schema, the versioned prompt pack, the one
bounded route-neutral complete-target call (the loopback structured-JSON provider plus the
oversize-only HTTPS client in the offline administrative pipeline) over the local
model, prompt, and routing policy, and the durable shared-execution/target-work/completion
contracts with their sole transaction-owning repository. It also owns candidate context: one neutral
canonical-JSON hasher, strict label-free target/candidate packet and multiview-fusion DTOs, the exact
read-only course-to-course candidate query over current compatible teaching chunks, one product-owned
label-free cross-encoder renderer/pair/scoring/selection kernel with its single hard final-candidate
ceiling, and the installed operational CE-only selection plus that bounded route-neutral
complete-target call. It also owns immutable accepted-result proposal composition and its
append-only repository: one completed validated completion becomes one versioned per-target proposal
with the direct-official dedup and its option flags, plus the cohort
publication adapter over the prerequisite package's inferred-set and equivalence-group repositories.

Publication is owned by this package's `publication.py`: one explicitly scoped, caller-proven
current cohort of accepted proposal pointers reads and validates the matching accepted proposals,
materializes the exact target inferred sets and global equivalence groups only through the
prerequisite package's inferred-set and equivalence-group repositories, withdraws inference-owned
output the cohort stops supporting, and reports scoped coverage through `diagnostics.py`. The
publisher runs no model, reranker, external route, or GPU work, never writes a final table directly,
validates the whole cohort before any write, and refuses a cohort that omits a target it already
published inferred output for.

Candidate context calls no inference model, targets no inactive course, excludes no inactive
candidate source, writes no run/work/completion row, publishes no inferred set or equivalence group,
and adds no administrative lifecycle. Field-view score is canonical cosine on the all-field match.
The fused reciprocal-rank score is label-blind selection evidence and no production model, prompt, or
routing policy is selected here. Model output is untrusted input: only a strict validated result is
written as a completion, and a rejected answer is failed and retried rather than accepted.
"""
