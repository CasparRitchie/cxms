# Level-crossing TD calibration

Field watch sessions are stored with a small snapshot of the Chichester Train
Describer feed. Calibration analysis is available at:

```text
/api/level-crossing/calibration-analysis/<crossing-id>
```

The endpoint is review-only. It groups observations into watch sessions and
compares newly appearing `CA`, `CB`, and `CC` berth events with the next gate
state recorded by the observer. It returns anonymous session sequences and
aggregate candidate transitions; notes, original session IDs, and complete TD
snapshots are not exposed.

Direction-labelled train observations are aggregated into each candidate's
`trainDirections` counts. Session timestamps are reduced to anonymous phase
durations, with medians and observed ranges returned in `timingModel`. These
support a shadow predictor without exposing the original observation times.

## Correcting rapid accidental taps

Original observations remain unchanged. During analysis, an `OPEN` tap is
treated as superseded when all of the following occur in one session:

1. The previous effective state was `CLOSED` or `TRAIN_PASSED`.
2. No `OPENING` was recorded first.
3. Another `CLOSED` or `TRAIN_PASSED` observation follows within 120 seconds.

This also covers a mistaken `OPEN` immediately followed by `TRAIN_PASSED`, then
`CLOSED`, as recorded in the fourth Whyke Road session. The analyser removes
only the mistaken `OPEN` from its effective sequence and reports the correction
in `correctionsApplied`.

## Activation rule

Candidate transitions are ranked by repetition across independent watch
sessions. `predictionUse` remains `review_only`; no candidate changes the
public prediction until its berth sequence has been manually reviewed and a
separate configuration explicitly activates it.

The first prediction implementation should remain in shadow mode and favour a
deterministic signalling state machine. A statistical timing model can estimate
closing and reopening intervals once enough independent sessions exist. Any
future trained model must be evaluated primarily on false-open decisions, as
those would produce the most misleading journey advice.

## Experimental Whyke Road signal watch

The main page has a separate research panel showing the last candidate CA
movements seen by the live TD listener. It does not change route wait estimates,
the main crossing state, or road advice. The UI refreshes every 10 seconds and
keeps a short, per-process candidate event history. A dyno restart clears that
history. The interpretation expires after three minutes or immediately when
the feed is disconnected; neither silence nor a clearing berth implies OPEN.

Candidate interpretations: `0094→0090` possible future closure, `0090→0086`
possible closure, `0086→0084` and `0085→0087` possible train passage,
`0087→0091` possible reopening. These are hypotheses, not direct barrier
telemetry. In particular, there is no validated Barnham-side advance warning.
Compare the displayed event clock times with the audible warning or a safely
observed gate state; do not use this panel to make a driving decision.
