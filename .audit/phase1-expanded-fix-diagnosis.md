# Expanded screen failure diagnosis

The expanded Bonsai 2 screen remains blocked at 12 of 16 checkpoints. The local scorer reran against the retained synthetic output and the pinned `rules+gliner` detector. The nine negative controls pass.

## Failure causes

At `registration-and-format-updated` and `remote-option-added`, GLiNER returns spans `84` and `68` with label `pin`. The source calls them the current and outdated registration counts. The scorer applies every non-date detector label to both fact text and evidence quotes, so it withholds these useful facts.

At `brief-completed`, the model does not report that the brief was sent. It repeats the workshop date and prior content requirements instead. The required completion fact is in the newest synthetic message, but it is absent from the model output.

At `announcement-paused`, the model emits the previous December 9 to December 16 launch change after the newest message says the launch is postponed. The scorer flags this stale, unreviewed fact. The separate pause fact passes.

## Safe-fix decision

No safe change in the current scorer or reviewed labels can clear all three failures. Whitelisting the numeric spans based on nearby registration wording would weaken the privacy boundary that treats possible PINs as sensitive. Omitting the numeric value would fail the existing reviewed expected fact, and changing that adjudication to fit the output would change the acceptance target. Prompt edits could target completion and temporal state, but they cannot resolve the independent detector conflict without new model output and fresh review. No prompt, detector, scorer, or label changes were made.

Rerun the local scorer and negative controls with:

```sh
PYTHONPATH=scripts .venv-eval/bin/python scripts/score_bonsai2_threads.py \
  --run-dir .audit/model-quality-trials/ternary-bonsai-2-27b-mlx-expanded-screen \
  --output .audit/model-quality-trials/ternary-bonsai-2-27b-mlx-expanded-screen/reviewed-thread-semantic-gate.json
PYTHONPATH=scripts .venv-eval/bin/python scripts/verify_bonsai2_thread_gate.py
```

The scorer reports 12 of 16 checkpoints and no complete gate pass. The verifier reports `negative_controls: 9`, `passed: 9`, and `screen_gate_passed: false`. Product inference remains disabled. No OAuth credentials were created, Gmail was not connected, and no account was accessed.
