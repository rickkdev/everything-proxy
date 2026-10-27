# Phase 1 evaluation design

## Reproducible commands

Detector profiles share one scorer and synthetic fixture set:

```sh
.venv-eval/bin/python scripts/evaluate.py --fixtures fixtures/email-evaluation.json --detector rules --output .audit/rules-expanded-report.json
.venv-eval/bin/python scripts/evaluate.py --fixtures fixtures/email-evaluation.json --detector rules+gliner --output .audit/rules-gliner-expanded-report.json
.venv-eval/bin/python scripts/evaluate.py --fixtures fixtures/email-evaluation.json --detector rules+privacy-filter --output .audit/rules-privacy-filter-expanded-report.json
.venv-eval/bin/python scripts/evaluate.py --fixtures fixtures/email-evaluation.json --detector rules+presidio --output .audit/rules-presidio-expanded-report.json
```

The local language-model run is separate:

```sh
.venv-eval/bin/python scripts/evaluate_qwen.py --candidate qwen3-4b-q4km --prompt-version 4-empty-noninclude --fixtures fixtures/email-evaluation.json --output .audit/qwen-v4-report.json
.venv-eval/bin/python scripts/evaluate_qwen.py --candidate qwen3-1_7b-q8_0 --prompt-version 4-empty-noninclude --fixtures fixtures/email-evaluation.json --port 18110 --output .audit/qwen-1_7b-v4-report.json
.venv-eval/bin/python scripts/evaluate_qwen.py --candidate qwen3-4b-q4km --prompt-version 4-empty-noninclude --privacy-detector rules+gliner --fixtures fixtures/email-evaluation.json --port 18117 --output .audit/qwen-v4-gliner-expanded-report.json
.venv-eval/bin/python scripts/evaluate_qwen.py --candidate qwen3-4b-q4km --prompt-version 4-empty-noninclude --privacy-detector rules+privacy-filter --fixtures fixtures/email-evaluation.json --port 18116 --output .audit/qwen-v4-privacy-filter-expanded-report.json
```

Model files are downloaded explicitly by `scripts/download_models.py` at revisions recorded in `model-lock.json`. Inference uses local model files and a llama.cpp server bound to `127.0.0.1`. Reports contain fixture IDs and aggregate/per-message counts, not source messages, extracted fact text, or detected span text.

## Scoring boundaries

- Detector scores count coverage of expected prohibited disclosure spans and exact predicted spans. This measures span matching on the fixture labels; it does not prove anonymity or real-world privacy.
- Qwen relevance is exact label agreement. Fact scoring counts predicted facts, evidence that is a nonempty exact substring of the source, evidence exactly matching a gold eligible-fact evidence string, and normalized exact canonical fact-text matches. Canonical text matching casefolds, normalizes whitespace, and strips one trailing period. It is a conservative lower bound, not a semantic equivalence score.
- The Qwen report records the prompt version because the same pinned weights are evaluated with explicit policy revisions.
- A fact is counted eligible only if relevance is `include`, evidence is nonempty and present in the source, the privacy detector reports no span, and no fixture prohibited string appears in generated text. Empty evidence cannot pass as a substring. The prohibited-string comparison is exact after normalization and does not judge semantic leakage.
- The Qwen run does not judge semantic correctness, unsupported implications, alias consistency, or every privacy leak. Exact canonical fact-text matches are deliberately strict; a zero does not prove every generated fact is wrong.
- Unsupported fixture languages are withheld before the prompt and count separately.
- The reviewed corpus has 12 synthetic messages, 11 scored English messages and one unsupported French message withheld before inference. All scores are exploratory and cannot justify a production quality claim.

## Expanded corpus findings

- Detector reports use 68 prohibited-span labels. Rules covered 39, GLiNER plus rules covered 42, Privacy Filter plus rules covered 56, and Presidio plus rules covered 41. Privacy Filter had 51 extra spans compared with 9 for GLiNER and 9 for Presidio. These small-corpus counts show a coverage/over-detection tradeoff, not a privacy guarantee.
- Qwen3-4B prompt v4 matched relevance on 10/11 messages, produced 14 facts versus 7 expected, and had zero exact canonical fact-text matches. The GLiNER profile counted 8 eligible facts; Privacy Filter counted 9. Prompt v5 did not improve the evidence: 10/11 relevance matches, 16 generated facts, zero exact canonical matches, 5 eligible facts, and one prohibited match remained after checks. Prompt v4 stays the default exploratory prompt.
- Qwen3-1.7B prompt v4 matched relevance on 7/11 and produced zero facts. No model candidate is selected for product processing. Model output remains a local proposal only, requiring per-fact user approval and a final independent privacy check if a future pipeline is accepted.
- All figures are one-run exploratory results on the current MacBook target (macOS arm64 with 36 GiB RAM). They do not establish repeatable behavior, long-thread handling, cross-platform behavior, or production privacy.

## Measurements

The detector runner samples system used memory and process peak RSS during model initialization and inference. The Qwen runner samples total system use and llama-server RSS every 100 ms, records model initialization, mean warm request time, serial messages per minute, model revision, and host memory. Queue delay is not applicable because this evaluator processes one request at a time without a work queue. The model file size is a download-size reference only. A single run on this host cannot establish cross-platform memory fit, target-machine fit, or stable throughput.

## Bonsai candidate comparison

Pinned and evaluated Bonsai 1.7B Q1_0 (1-bit, 248,302,272-byte GGUF) and Ternary-Bonsai 1.7B Q2_0 group-64 (1.58-bit, 490,163,968-byte GGUF) with the same prompt v4, fixtures, local llama.cpp server, and GLiNER privacy profile. The checkpoint revisions are in `model-lock.json`.

| Candidate | Relevance | Facts | Exact fact text | Evidence | Eligible with detector | Detector misses withheld by fixture guard | Peak model RSS |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Bonsai 1.7B Q1_0 | 0/11 | 15 | 1 | 13 valid, 2 unsupported | 0 | 0 | 0.84 GB |
| Ternary-Bonsai 1.7B Q2_0 g64 | 8/11 | 23 | 1 | 20 valid, 3 unsupported | 6 | 2 detector misses | 1.21 GB |

Both are single exploratory runs. The Q1_0 run had 11 output parse/schema errors, one exact fact-text match, and zero relevance matches. A separate harmless short JSON request returned valid JSON, which rules out a universal server-startup failure. The report does not retain generated text, so it cannot distinguish prompt-following errors from model limitations. The ternary candidate was also run with `rules+privacy-filter`; it remained 8/11 on relevance, generated 23 facts with one exact fact match and three unsupported evidence spans, and produced 7 eligible facts. Privacy Filter missed one exact fixture prohibited-string mention in generated text, but the separate fixture-string gate kept that fact out of the eligible count. The GLiNER profile missed two such mentions, and that gate also kept those facts out of the eligible count. Neither run is acceptable for automatic release.

Peak system memory was sampled on the 36 GiB MacBook target. Observed system-used samples around 15.7 to 15.9 GB leave substantial headroom in these single runs, but do not establish repeatability or long-thread behavior. Process RSS and serialized inference time are from one run per candidate; no stable speed or throughput claim is made. The smaller file size is a download-size reference only. Neither candidate is selected. The ternary run suggests a utility direction worth retuning, but it does not clear relevance, fact support, privacy, repeatability, or MacBook memory requirements.

## MacBook target follow-up

The target is Rick’s MacBook Pro (macOS arm64, 36 GiB installed memory). The local model evaluators now record detected host memory as `target_total_memory_bytes`, rather than the superseded 10 GiB assumption. Earlier reports retain their original 10 GiB `target_total_memory_bytes`; use their `host_total_memory_bytes` field for the actual MacBook capacity.

- A repeat Ternary-Bonsai v4 + GLiNER run reproduced 8/11 relevance matches, 23 generated facts against 7 expected, 6 eligible facts, and 3 unsupported evidence spans. Peak model RSS was 1.22 GB and peak system-used memory was 15.80 GB out of 36 GiB. See `.audit/ternary-bonsai-1_7b-q2_0-g64-v4-gliner-repeat1-report.json`; the earlier run is `.audit/ternary-bonsai-1_7b-q2_0-g64-v4-gliner-report.json`.
- Ternary-Bonsai prompt v5 scored 6/11 relevance, generated 19 facts against 7 expected, had 4 unsupported evidence spans and one prohibited mention remaining after detector checks. It did not improve quality. See `.audit/ternary-bonsai-1_7b-q2_0-g64-v5-gliner-report.json`.
- A synthetic thread-shaped message with 24 earlier notes and a current action has a 5,081-character body. With a 4,096-token context, Ternary-Bonsai v4 returned valid JSON, matched the include label, produced 2 facts against 1 expected, and took 1.82 seconds. Peak model RSS was 1.09 GB and peak system-used memory was 16.20 GB out of 36 GiB. This is a synthetic single-message context check, not multi-message thread behavior. See `fixtures/macbook-long-thread.json` and `.audit/ternary-bonsai-1_7b-q2_0-g64-v4-long-thread-report.json`.

These measurements establish the available MacBook memory for the tested cases, not a production memory margin under every app workload. Model quality still blocks pipeline selection and dependent production phases.

## Repeated 4B versus 8B comparison

The evaluator now reports `eligible_exact_expected_fact_text_count`: an exact canonical fact-text match counts only when the predicted relevance is `include`, the nonempty evidence is a source substring, the configured detector finds no sensitive span, and no fixture-specific prohibited disclosure appears. A synthetic scorer probe returned 1 for a valid exact fact and 0 when evidence was invalid, relevance was wrong, or fixture-prohibited text was present. The existing report schema was incremented to version 3. This metric is intentionally conservative and does not capture semantically equivalent paraphrases.

The frozen local command was:

```sh
.venv-eval/bin/python scripts/compare_model_quality.py --baseline qwen3-4b-q4km --candidate qwen3-8b-q4km --pairs 5
```

It ran 5 alternating pairs (10 total reports), with 11 scored messages per run, 55 scored messages per model, and zero runner errors. Both models used Qwen3 prompt v4, `rules+gliner`, 4,096 context, and the same synthetic fixture set on the 36 GiB arm64 MacBook. Medians across the five runs:

| Metric | Qwen3-4B baseline | Qwen3-8B candidate |
| --- | ---: | ---: |
| Eligible exact expected facts (of 7) | 0 | 0 |
| Relevance matches (of 11) | 10 | 9 |
| Generated facts (expected 7) | 14 | 16 |
| Facts surviving local privacy/evidence gates | 8 | 12 |
| Unsupported evidence | 0 | 0 |
| Prohibited mentions remaining after detector | 0 | 2 |
| Parse errors | 0 | 0 |
| Process peak RSS | 3.27 GB | 5.69 GB |
| Peak system-used memory | 16.05 GB | 17.04 GB |

The 8B size hypothesis is rejected: it did not improve exact useful fact recovery and failed relevance, fact-count, and privacy guardrails in every candidate run. The 4B baseline itself also missed the exact-fact target in all five runs, though its other measured guardrails held. Full per-run reports and the aggregate are in `.audit/model-quality-trials/`; the model file was verified against its pinned SHA-256 before evaluation. This comparison does not judge semantic paraphrases or validate multi-message thread behavior. Keep inference disabled and Phase 1 open.

## Ternary-Bonsai 2 27B MLX evaluation

Rick requested a trial of [Ternary-Bonsai 2 27B MLX](https://huggingface.co/prism-ml/Ternary-Bonsai-2-27B-mlx-2bit). The checkpoint was pinned at revision `fcba37d2117a7077eac6b613b2668d14d9779edd` and its 8,595,477,990-byte weight file matched SHA-256 `130de5925082c168b7866b2e91b52e44abbafc99017e3ca352b77b5b55a269ed`. It ran through the publisher-documented native `mlx-vlm` stack in an isolated Python 3.12 environment; the [publisher's demo](https://github.com/PrismML-Eng/Bonsai-demo) documents this loader and its MLX runtime versions. The new `scripts/evaluate_bonsai2_mlx.py` keeps server lifecycle separate while reusing the existing prompt, fixtures, detector, and frozen scorer.

Five full passes used the same 12 synthetic fixtures (11 English scored, unsupported French withheld), for 55 scored messages and zero runner errors. The MLX non-thinking sampling profile was temperature 0.7, top-p 0.8, top-k 20, min-p 0, presence penalty 1.5 with a 64-token window, repetition penalty 1.0; context was 4,096 and output capped at 512 tokens.

| Metric (median, per run) | Qwen3-4B baseline, prior five-run trial | Ternary-Bonsai 2 27B MLX, five passes |
| --- | ---: | ---: |
| Eligible exact expected facts (of 7) | 0 | 0 |
| Relevance matches (of 11) | 10 | 10 |
| Predicted facts (expected 7) | 14 | 5 |
| Facts surviving local privacy/evidence gates | 8 | 1 |
| Unsupported evidence | 0 | 0 |
| Prohibited mentions remaining after detector | 0 | 0 |
| Parse errors | 0 | 0 |
| Process peak RSS | 3.27 GB | 3.38 GB |
| Peak system-used memory | 16.05 GB | 21.68 GB |

The candidate reached the relevance and privacy/evidence guardrails but failed the primary target of at least 4/7 eligible exact facts in every run. Exact text is a conservative lower bound; no generated text was retained, so semantic adequacy of paraphrases remains unmeasured. Memory samples are from separate sessions with different desktop load and are not a controlled comparison. The MLX process was loaded once and reused across the five passes. Keep this candidate rejected and inference disabled. Full counts and ranges are in `.audit/model-quality-trials/ternary-bonsai-2-27b-mlx/summary.json`; the pinned model registry entry and repeatable driver remain for local reproduction.

## Data shapes

`evaluate.py` defines `MessageFixture`, `ExpectedFact`, `ExpectedResult`, and `DetectedSpan` for the shared corpus and detector scorer. `evaluate_qwen.py` reports per-message relevance and evidence counts without retaining or printing generated fact text. Inference is served locally; the evaluator does not call an external model service.

## Synthetic usefulness, support, and privacy gate

The historical fact gate counted only normalized exact expected fact text. Its eligibility predicate also rejected every detector span, so a useful date fact failed even when the fixture did not mark that date as prohibited. It separately rejected literal fixture prohibited strings. Those checks explain exact-paraphrase false negatives and date-related false negatives; they do not provide a semantic equivalence judgment.

`scripts/verify_model_gate.py` exercises a proposed gate on nine synthetic output/evidence pairs. Usefulness is an explicit reviewed `meaning_equivalent` label, support requires nonempty evidence copied from the synthetic source, and privacy hard-fails any fixture-prohibited disclosure. The date-flag field recreates the former broad detector rejection so the before/after cases isolate its effect. A date flag alone is not a privacy violation in the proposed scoring. No model is loaded or called.

| Case | Before | After | Finding |
| --- | --- | --- | --- |
| exact-supported-fact | pass | pass | Exact supported fact remains accepted. |
| paraphrase-action | reject | pass | Equivalent paraphrase no longer needs exact wording. |
| paraphrase-deadline-change | reject | pass | Paraphrase preserves both dates and their direction. |
| ordinary-date-useful-fact | reject | pass | Ordinary date flag does not cause a privacy failure. |
| unsupported-claim | reject | reject | Added claim is not semantically approved. |
| wrong-meaning | reject | reject | Reversed date change is not equivalent. |
| unsupported-evidence | reject | reject | Evidence must occur in the source. |
| recovery-code-disclosure | reject | hard-fail | Prohibited recovery code always fails. |
| identity-disclosure | reject | hard-fail | Prohibited identity always fails even when useful. |

The run accepted 1/9 under the old exact-match-plus-any-date-flag rule and 4/9 under the proposed rule. Two cases hard-failed for prohibited disclosures. The new count is a property of this deliberately small synthetic suite, not a model quality estimate. `meaning_equivalent` is adjudicated fixture data here; this experiment does not implement an automatic semantic judge or prove the production PII detector's date behavior. Keep inference disabled. Before changing historical model comparisons, retain model outputs locally for reviewed synthetic semantic judgments or add reviewed candidate-specific labels; do not infer their semantic quality from the old zero-exact counts. Reproduce with `python scripts/verify_model_gate.py`.

## Bonsai 2 under the reviewed semantic gate

The pinned Bonsai 2 checkpoint was rerun for five passes on the same 12 synthetic fixtures, with inference served by the local pinned MLX runtime, prompt `4-empty-noninclude`, and `rules+gliner`. All 55 scored messages completed without runner or parse errors. Generated output contains synthetic fixture content only and is retained in `.audit/model-quality-trials/ternary-bonsai-2-27b-mlx-redesigned/`. `fixtures/bonsai2-semantic-adjudication.json` records reviewed exact-output-to-gold-equivalence annotations. `scripts/score_bonsai2_redesigned.py` checks those annotations, source evidence, prohibited fixture strings, and detector labels without calling a model.

The old gate reported zero exact eligible facts in every pass. Inspection showed five supported and useful generated facts in every pass. GLiNER labeled ordinary dates in four of them as generic `date`; the old eligibility rule rejected all four. The reviewed scorer reports those labels but does not treat a generic date label alone as prohibited privacy risk. The facts contain no fixture-prohibited strings. Bonsai also classified `security-alert-001` as `inspect` in every pass and omitted the expected security fact. This is a model error, not a gate error. Bonsai also omitted the second expected fact in `direct-request-001`.

| Metric per pass | Result | Gate interpretation |
| --- | ---: | --- |
| Reviewed useful facts with supported evidence | 5/7 | Passes the existing minimum of 4. |
| Relevance labels correct | 10/11 | Passes the existing minimum of 10. |
| Unsupported evidence | 0 | Pass. |
| Prohibited disclosures | 0 | Pass. |
| Parse or runner errors | 0 | Pass. |
| Reviewed semantic gate | 5/5 passes | Candidate clears this synthetic threshold. |

The five runs produced the same reviewed outputs, so the 5/7 and 10/11 results had no spread in this setup. Peak system-used memory ranged from 22.73 to 23.00 GB on the 36 GiB host; process RSS was 3.38 GB in all runs. These figures establish only this repeated synthetic run, not production readiness or multi-message long-thread behavior. The model passes the revised synthetic candidate gate, but remains unselected because the fixture set is small and the missed security alert matters. Keep product inference disabled pending prompt/model work on that miss and broader reviewed coverage. Reproduce inference with `scripts/evaluate_bonsai2_mlx.py --runs 5 --prompt-version 4-empty-noninclude --privacy-detector rules+gliner --output-dir .audit/model-quality-trials/ternary-bonsai-2-27b-mlx-redesigned`, then reproduce reviewed scoring with `PYTHONPATH=scripts .venv-eval/bin/python scripts/score_bonsai2_redesigned.py --run-dir .audit/model-quality-trials/ternary-bonsai-2-27b-mlx-redesigned`.

## Bonsai 2 security alert prompt follow-up

The previous section records the prompt-v4 miss. The new fail-closed gate requires `security-alert-001` to be classified `include` with a reviewed-equivalent fact whose exact evidence quote occurs in the source. It also requires both reviewed changed-date facts and counts only distinct gold facts from included cases. Each included case may return at most two facts; non-include cases must return none. The gate fails on prohibited fixture strings anywhere in returned text, unsupported or unreviewed evidence, non-date detector review spans, schema/coverage errors, parse errors, runner errors, or insufficient aggregate usefulness and relevance. A generic `date` detector label alone remains allowed; exact reviewed adjudication still checks its meaning and direction.

Two prompt variants were screened for one full pass each. `6-security-scope` says a blocked or suspicious sign-in remains relevant even when credentials appear, while secrets remain excluded from facts and evidence. `7-security-split` separates event relevance from fact disclosure and explicitly requires including blocked or suspicious sign-ins. Both passed the reviewed semantic gate with 6/7 useful supported facts and 11/11 relevance. Variant 6 emitted seven facts; variant 7 emitted eight. The one-run process RSS and system-used samples are exploratory, not a reliable memory comparison. Variant 6 was selected for five repeated runs because its prompt states the targeted rule more narrowly and produced one fewer fact.

Variant 6 passed the reviewed gate in all five repeat runs on the pinned checkpoint. Each run covered 11 English messages from 12 loaded fixtures and withheld the unsupported French fixture. Each scored 6/7 reviewed useful facts, 11/11 relevance, and zero unsupported evidence, prohibited disclosures, non-date privacy review spans, parse errors, or runner errors. The security alert and both changed-date cases passed every time. Peak process RSS was 6.75 GB and peak system use was 22.70 GB out of 36 GiB. All five output files have the same SHA-256. The legacy exact canonical count remains 0/7, and its separate exact-match gate flag remains false.

Case-by-case reviewed outcomes, screening outputs, repeated output files, measurements, and commands are in `.audit/bonsai2-security-review.md` and `.audit/model-quality-trials/`. Prompt 6 still misses the second direct-request fact. The synthetic corpus remains small, and multi-message long-thread behavior remains unverified. Keep product inference disabled and broaden reviewed coverage before selecting a pipeline.

## Ordered multi-message thread evaluation

Added three synthetic threads with two ordered messages each. Each thread has two checkpoints. The evaluator sends the full visible message prefix for every checkpoint, so later outputs can revise a deadline, complete a request, or add context to a security alert. The reviewed gate binds each fact to exact evidence and message IDs, checks the prefix IDs and hash, rejects unsupported or stale facts, and scans returned text for prohibited disclosures. The existing single-message gate remains unchanged.

The pinned Bonsai 2 checkpoint ran five times with `thread-1-current-state`, 4,096 context tokens, 384 output tokens, and `rules+gliner`. Every run passed all three thread cases and six checkpoints with no runner errors. All five output files have SHA-256 `baf0e3ceeef71dfe6da6a6dcfe38111a1b596838e151586b5f053689892d9105`.

| Thread case | Checkpoints | Result in every run |
| --- | ---: | --- |
| `deadline-revision-thread-001` | 2 | Recovered the initial date, then replaced it with the revised date. |
| `request-completion-thread-001` | 2 | Reported the open request, then its completed state. |
| `security-context-thread-001` | 2 | Included the blocked sign-in, omitted the recovery code, and incorporated the account owner's follow-up. |

The MacBook reported 36 GiB total memory. The sampler recorded 3,736,453,120 bytes process RSS and 22,142,500,864 bytes system-used at peak. These are cumulative high-water samples from one server process across detector initialization, model load, warmup, and all five repeated runs. They are not independent per-run memory samples and do not establish production memory fit.

Case-level outcomes, evidence, and memory measurements are in `.audit/model-quality-trials/ternary-bonsai-2-27b-mlx-threads/reviewed-thread-semantic-gate.json` and `thread-summary.json`. Nine negative controls pass in `scripts/verify_bonsai2_thread_gate.py`. Reproduce the model run with `.venv-eval/bin/python scripts/evaluate_bonsai2_threads.py --runs 5 --port 18233 --output-dir .audit/model-quality-trials/ternary-bonsai-2-27b-mlx-threads`, then score it with `.venv-eval/bin/python scripts/score_bonsai2_threads.py --run-dir .audit/model-quality-trials/ternary-bonsai-2-27b-mlx-threads --output .audit/model-quality-trials/ternary-bonsai-2-27b-mlx-threads/reviewed-thread-semantic-gate.json`.

This result covers three synthetic thread patterns and one pinned model/prompt combination. Product inference remains disabled. More coverage and a separate pipeline decision remain open.

## Expanded five-message thread screen

Added two reviewed cases with five messages each. `workshop-brief-thread-001` covers a revised event date, an updated registration count, new content requirements, and completion. `announcement-pause-resume-thread-001` covers a revised launch date, a pause, a new confirmed date, and completion. The full fixture now has five cases, 16 messages, 16 checkpoints, and a longest thread of five messages. Each checkpoint has expected current facts and source evidence, plus stale or resolved fact constraints where they apply. See `fixtures/thread-evaluation.json` and `fixtures/thread-semantic-adjudication.json`.

The pinned Ternary-Bonsai 2 27B MLX candidate was screened once with prompt `thread-1-current-state`, a 4,096-token context, a 384-token output limit, and `rules+gliner`. The local runner completed all 16 checkpoints without errors. The reviewed gate passed 12 of 16 checkpoints across three of five cases. It failed the workshop brief at the count and completion checkpoints because GLiNER marked the useful registration count `84` as a PIN, and the thread summary omitted that the brief was complete. It failed the announcement pause checkpoint because it repeated a launch target that the latest message had postponed. These failures remain in the expected results; no adjudication label converts them into passes.

The single-run cumulative high-water sample was 2,259,615,744 bytes process RSS and 22,031,941,632 bytes system-used on a 38,654,705,664-byte host. This is a screening sample, not a repeatable memory or latency result and not proof of production fit. The existing product inference path remains disabled. Reproduce the screen with `.venv-eval/bin/python scripts/evaluate_bonsai2_threads.py --runs 1 --port 18234 --output-dir .audit/model-quality-trials/ternary-bonsai-2-27b-mlx-expanded-screen`, then score it with `.venv-eval/bin/python scripts/score_bonsai2_threads.py --run-dir .audit/model-quality-trials/ternary-bonsai-2-27b-mlx-expanded-screen --output .audit/model-quality-trials/ternary-bonsai-2-27b-mlx-expanded-screen/reviewed-thread-semantic-gate.json`. The runner contacts only its loopback MLX server and runs with Hugging Face offline flags. `scripts/verify_bonsai2_thread_gate.py` passes nine negative controls against the expanded coverage and retained screen outputs.
