# SafeTrace In-Car Violation Capabilities

SafeTrace contains rule-level support for several in-car safety checks, but a
rule can only fire when the detector produces the required labels and masks.
Do not claim production support for seatbelt or phone-use detection unless a
local evaluation run demonstrates the current pipeline output on representative
footage.

## Current Rule Coverage

- `seatbelt_missing`: requires person/torso evidence and missing or weak
  seatbelt overlap.
- `phone_use`: requires a phone region overlapping a hand region.
- `hands_off_steering_wheel`: requires hand and steering-wheel regions.
- `helmet_missing`: requires person/head and helmet regions.

Generic detector checkpoints may not reliably detect seatbelts, phones, hands,
steering wheels, or torso regions in vehicle interiors. Rule-based support is
therefore not the same as verified detector capability.

## Local Evaluation

Run:

```cmd
python scripts\evaluate_in_car_violations.py --samples-dir data\manual_eval
```

The script looks for normalized SafeTrace result JSON files under the samples
directory. If no samples are present, it exits successfully and reports
`NOT_TESTED_NO_SAMPLE`.

Status meanings:

- `PASS`: at least one supplied SafeTrace result JSON contains the target
  violation output.
- `UNSUPPORTED`: supplied result JSON files did not contain the target
  violation output. This is not a detector benchmark failure unless the samples
  include labeled ground truth.
- `FAIL`: reserved for a future labeled-ground-truth evaluator.
- `NOT_TESTED_NO_SAMPLE`: no local sample output was provided.

## Recommended Manual Evaluation Set

For future verification, collect local-only sample videos or result JSON files
covering:

- driver wearing a seatbelt,
- driver not wearing a seatbelt,
- driver holding or using a phone,
- driver with hands away from the steering wheel,
- normal driving without the target violations.

Keep uploaded videos, generated frames, reports, and model assets out of git.
