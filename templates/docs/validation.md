# Validation and systematics

{{ dry_banner }}

All values on this page are **observed** on the production sample and generated from `results/production.json`.
Benchmarks are labelled as such. Scans use the channel's validation model, which has one resolution core, because each
scan entry has fewer pairs than the inclusive sample; their reference is the same model on all pairs. Entries need at
least {{ z.min_pairs }} pairs (the controlling benchmark for validation pairs per category).

`d/s` is the difference from that reference in units of the raw statistical error; `S` is the scale factor
sqrt(χ²/ndf), floored at one, and `d/s scaled` uses the scaled error. A large `d/s` means the peak depends on the
category, which uncorrected momentum scales can produce. Values are reported as they came out.

## Benchmarks and observed values

{{ targets_table }}

## Every benchmark in the registry

{{ registry_table }}

{{ registry_not_met }}

## Summary

{{ systematics_table }}

## Run-period consistency (T6)

{{ periods_table }}

## Z: scans

{{ z.validation_table }}

## Z: fit-choice stability

{{ z.fit_choice_table }}

{{ z.fit_choice_failed }}

## Z: per-file fits (files by index)

{{ z.per_file_table }}

## Z: cutflow

{{ z.cutflow_table }}

## Z: warnings

{{ z.warnings }}

## J/ψ: scans

{{ jpsi.validation_table }}

## J/ψ: fit-choice stability

{{ jpsi.fit_choice_table }}

{{ jpsi.fit_choice_failed }}

## J/ψ: per-file fits (files by index)

{{ jpsi.per_file_table }}

## J/ψ: cutflow

{{ jpsi.cutflow_table }}

## J/ψ: warnings

{{ jpsi.warnings }}
