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

## Correcting rapid accidental taps

Original observations remain unchanged. During analysis, an `OPEN` tap is
treated as superseded when all of the following occur in one session:

1. The previous effective state was `CLOSED` or `TRAIN_PASSED`.
2. `CLOSED` is tapped within 30 seconds of `OPEN`.
3. `TRAIN_PASSED` follows within 120 seconds of that `OPEN` tap.

The analyser removes only the mistaken `OPEN` from its effective sequence and
reports the correction in `correctionsApplied`.

## Activation rule

Candidate transitions are ranked by repetition across independent watch
sessions. `predictionUse` remains `review_only`; no candidate changes the
public prediction until its berth sequence has been manually reviewed and a
separate configuration explicitly activates it.
