# Synthetic model gate redesign

- [x] Diagnose current scoring failures from the evaluator and recorded results.
- [x] Define a synthetic case format with independent usefulness, evidence-support, and privacy outcomes.
- [x] Implement a deterministic gate with semantic paraphrase labels and hard privacy failures.
- [x] Run the gate on synthetic positive and negative cases with inference disabled.
- [x] Record before/after case results, decisions, limits, and the next unchecked task.

Next: retain future local model output for reviewed semantic scoring, or add candidate-specific reviewed equivalence labels. Do not reinterpret historical exact-match reports as semantic judgments.

## Bonsai 2 follow-up

- [x] Preserve the five local synthetic Bonsai 2 outputs for semantic review.
- [x] Review paraphrases against expected facts, source evidence, detector spans, and prohibited disclosures.
- [x] Separate date-detector false positives from the model's security-alert relevance miss.
- [x] Record the revised per-run gate result and keep product inference disabled.

Throughput checkpoint:

- Blocking first steps: run the pinned model and preserve outputs before adjudicating meaning.
- Independent workstreams: n/a, one model run and its adjudication share the same fixture IDs and outputs.
- Shared mutable state: n/a, a single local output directory owns all five runs.
- Smallest safe decomposition: one engineer owns the evaluation because inference results must be tied directly to the reviewed outputs.

Next: improve the missed synthetic security-alert classification or evaluate another candidate. Keep product inference disabled.

Throughput checkpoint:

- Blocking first steps: inspect existing scoring and identify false rejection mechanisms before changing the gate.
- Independent workstreams: n/a, one evaluator and case file must share one rubric.
- Shared mutable state: n/a, one writer owns the case file and evaluator.
- Smallest safe decomposition: one engineer can complete this bounded synthetic scorer without fan-out.
