"""Package boundary for inference: result, prompt, candidate, evidence and publication contracts.

The modules define the strict complete-target result and versioned prompt contracts, the label-free
target and candidate packets, the cross-encoder selection kernel, the route-budgeted target writer,
and the evidence repository, the proposal repository and the publication adapter. Publication
materializes an accepted cohort through the prerequisite package's repositories for inferred sets
and equivalence groups, and canonical digests come from the shared canonical-JSON hasher in
``course_explorer.hashing``. Local routes come from the validated settings, and a caller injects an
``OversizeRouteFactory`` for a packet that fits no ordered local key. Model output is untrusted
input and becomes a completion only after strict validation.
"""
