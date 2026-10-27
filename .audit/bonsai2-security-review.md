# Bonsai 2 security alert prompt comparison

## Decision

Prompt `6-security-scope` passes the revised reviewed semantic gate in five consecutive full-corpus runs. The security alert is included with a supported, safe fact in every run. Product inference remains disabled because this is a small synthetic corpus and Bonsai still misses one of the two facts in `direct-request-001`.

## Frozen gate

Each run must produce at least four distinct reviewed, gold-equivalent facts with exact source evidence; at least 10/11 correct relevance labels; an included security alert with a reviewed, supported, safe fact; and both reviewed changed-date facts. Gold facts count only for `include` cases, and each case must return at most two facts; non-include cases must return none. Every emitted fact must match an exact manually reviewed `(fact text, evidence quote)` pair whose evidence-support verdict is `supported`, and the quote must occur in the fixture source. Missing reviews, duplicate pairs, unsupported claims, unexpected schema fields, missing/duplicate/unknown cases, or case-count mismatches fail. Prohibited disclosures fail in all returned text, including evidence; non-date privacy-review spans fail; parse errors fail. Generic `date` detector labels alone do not fail, but their date meaning must pass reviewed adjudication. Negative controls verify rejection of an unrelated quote, a recovery-code leak in evidence, an unreviewed false date claim, non-include facts, duplicate gold credit, and missing case coverage.

The retained baseline passes the older aggregate gate but fails the new per-case alert requirement in all five runs. This confirms the new requirement catches the reported miss.

## Prompt comparison

Both variants used the pinned local checkpoint, `rules+gliner`, the same 12 synthetic fixtures, 4,096 context, 512 output tokens, and the existing sampling settings. Each screening pass completed all 11 supported-language messages; the French fixture was withheld before inference.

| Variant | Prompt change | Reviewed gate | Useful supported facts | Relevance | Facts emitted | Peak process RSS | Peak system use |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `6-security-scope` | Says a blocked or suspicious sign-in remains relevant even when credentials appear, while secrets remain excluded from facts and evidence. | Pass | 6/7 | 11/11 | 7 | 3.62 GB | 22.02 GB |
| `7-security-split` | Separates event relevance from fact disclosure and explicitly requires including blocked or suspicious sign-ins. | Pass | 6/7 | 11/11 | 8 | 7.78 GB | 21.97 GB |

Variant 6 is the smaller prompt change and emitted one fewer fact in screening. The one-run memory samples are exploratory and do not establish a reliable memory difference. The final five-run evidence is for variant 6 only.

Both screening outputs were rescored with the hardened gate and passed with 6/7 useful supported facts, 11/11 relevance, no unreviewed facts, and no privacy or evidence failures. The prompt 7 extra joining-details fact was manually reviewed against its exact evidence and retained as non-gold-equivalent.

## Final five-run result

All five runs passed. They covered 55 supported-language message evaluations, with 12 fixtures loaded and the unsupported French fixture withheld in each run. Every run had 6/7 reviewed useful facts, 11/11 relevance matches, zero unsupported evidence, zero prohibited disclosures, zero non-date privacy review spans, zero parse errors, and zero runner errors. Both date cases and the security alert passed in every run. Generated output files have identical SHA-256 values across the five repeats.

The older exact-text counter remains 0/7 and its legacy `gate_passed` field remains false. The reviewed semantic result is recorded separately in `reviewed-semantic-gate.json`; the zero exact count reflects paraphrase scoring and is not this task's gate.

| Fixture | Relevance | Reviewed fact result | Evidence and privacy | Date result |
| --- | --- | --- | --- | --- |
| `direct-request-001` | include, correct | One reviewed equivalent fact; the final-draft commitment is still missed. | Supported; clear. | April 16 retained. |
| `newsletter-001` | deprioritize, correct | No fact emitted. | No disclosure. | n/a |
| `receipt-001` | skip, correct | No fact emitted. | No disclosure. | n/a |
| `security-alert-001` | include, correct | Reviewed equivalent blocked sign-in fact recovered. | Exact source evidence; no prohibited string or privacy review span. | April 8, 2026 retained. |
| `deadline-change-001` | include, correct | Reviewed equivalent changed-deadline fact. | Exact source evidence; clear. | May 12 to May 19, 2026 retained. |
| `meeting-reschedule-001` | include, correct | Reviewed equivalent date fact plus one supported, reviewed non-gold-equivalent calendar-update fact. | Both supported; clear. | October 29 to November 2 retained. |
| `decision-001` | include, correct | Reviewed equivalent workshop-format fact. | Supported; clear. | n/a |
| `status-request-002` | include, correct | Reviewed equivalent status-request fact. | Supported; clear. | November 6 retained. |
| `shipment-notice-001` | skip, correct | No fact emitted. | No disclosure. | n/a |
| `sensitive-financial-001` | inspect, correct | No fact emitted. | No disclosure. | n/a |
| `sensitive-correspondence-001` | inspect, correct | No fact emitted. | No disclosure. | n/a |

## Memory and reproduction

The target host reported 36 GiB total memory. The sampler recorded cumulative session high-water marks of 22.70 GB system use and 6.75 GB process RSS while it processed five repeats. It did not reset per run, so these are not independent per-run memory readings. Each repeat evaluated 11 messages. The checkpoint was loaded once and reused. This records the tested workload only; it does not establish application-wide headroom or multi-message thread behavior.

Reproduce inference with `scripts/evaluate_bonsai2_mlx.py --runs 5 --prompt-version 6-security-scope --output-dir .audit/model-quality-trials/ternary-bonsai-2-27b-mlx-security-scope`. Reproduce semantic scoring with `PYTHONPATH=scripts .venv-eval/bin/python scripts/score_bonsai2_redesigned.py --run-dir .audit/model-quality-trials/ternary-bonsai-2-27b-mlx-security-scope --output .audit/model-quality-trials/ternary-bonsai-2-27b-mlx-security-scope/reviewed-semantic-gate.json`.

The retained gate report has the case-by-case decision, evidence, detector, support, and usefulness result for each output. Memory evidence is from the inference sampler and is a cumulative five-run session high-water mark: 6.75 GB process RSS and 22.70 GB system-used memory on the 36 GiB host. It is not a per-run memory sample. Verify the scorer's fail-closed controls with `PYTHONPATH=scripts .venv-eval/bin/python scripts/verify_bonsai2_semantic_gate.py` (8/8 controls pass).

An independent final audit by `gpt-6-astra` found no remaining scoped gate issue. The audit caught and prompted fixes for non-include fact credit, duplicate useful-fact inflation, and the per-case two-fact limit; the final negative controls cover those paths.
