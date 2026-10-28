# Candidate review: completed workshop brief

The retained `brief-completed` output includes the correct relevance value but omits `brief-complete-current-details`. It repeats the old workshop-date change and the earlier brief requirements. The gate records the expected fact as missing and reports two unreviewed facts, two unsupported evidence pairs, and two privacy-review facts.

## Proposed candidate output

```json
{
  "relevance": "include",
  "facts": [
    {
      "text": "The partner workshop brief was sent with the current count, hybrid format, and remote attendance option.",
      "evidence": [
        {
          "message_id": "workshop-brief-001-m5",
          "quote": "I sent the brief today. It has 84 registrations, a hybrid format, and a remote attendance option."
        }
      ]
    }
  ]
}
```

This is a proposed review item, not model output or an adjudication. The quote comes from the latest synthetic message, which also says participant names were left out and the brief is complete. The expected fact intentionally summarizes those details without including a precise count.

## Review required

The source quote contains `84`. Earlier checkpoints in this thread had the pinned GLiNER detector label `84` and `68` as `pin`; the existing gate marked facts containing those spans `privacy_risk: review`. The proposed output therefore needs the existing privacy checks applied unchanged. This record does not claim the output passes disclosure review or should be released.

No fixture, reviewed label, adjudication, model output, or privacy check was changed. Product inference remains disabled pending the review decision and resolution of the expanded-screen blocker.
