# Synthetic browser checkpoint layouts

Both concepts use fixture data only. Evaluation reference facts are visibly labelled and cannot be approved or released.

## Option A. Inbox list and selected message

```text
┌──────────────────────────────────────────────────────────────────┐
│ Everything Proxy                         SYNTHETIC DEMO · local only│
├───────────┬─────────────────────┬────────────────────────────────┤
│ Search    │ Messages            │ Selected message               │
│ Digest    │                     │                                │
│ All 12    │ Direct request      │ Source preview                 │
│ Included  │ Meeting change      │                                │
│ Review    │ Receipt             │ Evaluation references          │
│           │ ...                 │ Privacy status · unavailable   │
└───────────┴─────────────────────┴────────────────────────────────┘
```

Strength: keeps source and evaluation references in the same view, making it obvious what is input and what is expected output. Weakness: three columns compress on smaller screens.

## Option B. Digest feed and source drawer

```text
┌──────────────────────────────────────────────────────────────────┐
│ Everything Proxy                         SYNTHETIC DEMO · local only│
├───────────────────────────────────────────────┬──────────────────┤
│ Search · Digest · Filters                      │ Source drawer    │
│                                               │                  │
│ Evaluation reference card                     │ Selected source  │
│ Evaluation reference card                     │                  │
│ Evaluation reference card                     │ Expected facts   │
│                                               │                  │
└───────────────────────────────────────────────┴──────────────────┘
```

Strength: gives digest content more room and reads well as a feed. Weakness: source context is hidden until a card opens, which can blur whether a statement came from the message or the evaluation labels.

## Selection

Use Option A for the checkpoint. Its explicit source and reference panes better serve the privacy-review task. Narrow-window drawer behavior is future work; the current CSS only adjusts column widths and does not collapse the message list. Revisit after Rick tests the browser view.
