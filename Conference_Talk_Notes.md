# Conference Talk Notes
**Paper:** A Privacy-Aware Web Dashboard for Comparative Community Energy Analytics Using Simulated Smart Circuit Controller Data
**Authors:** Bongani Nyoni (260119806), Mr. M Ratshitanga (Supervisor)
**Deck:** `Bongani_Nyoni_260119806.pptx` (12 slides)
**Target length:** about 15 to 20 minutes talk plus Q&A (roughly 1.5 min/slide)

General delivery notes:
- Speak to the room, not the slide. The numbers are there for people to read; your job is to explain what they mean.
- If a question runs long, it's fine to say "that's covered in the paper, happy to discuss after" rather than derailing your time.
- Where a slide has a caveat line (for example "not yet profile-matched" or "requires reconciliation"), say it out loud yourself before someone else points it out. It reads as confidence, not weakness.

---

## Slide 1: Title
**On screen:** Paper title, your name and student number, supervisor, department and university.

**Say:**
"Good [morning/afternoon]. This talk is about turning raw circuit-level electricity readings into comparisons people can actually act on: things like 'is my use rising,' 'which appliance is driving my bill,' and 'is this normal for a home like mine.' I built and technically evaluated a full pipeline and dashboard for that, using a simulated smart circuit controller, and I'll walk through the problem, the design, the results, and what's still open."

**Timing:** About 45 seconds. This is the hook, not the content.

---

## Slide 2: The Problem (readings are not insights)
**On screen:** Voltage/current/power readings don't explain behaviour; households need rankings, peaks, cost estimates and fair comparisons; commercial controller APIs aren't always accessible for research; the goal is a testable interpretation layer, not a billing system.

**Say:**
"A raw voltage, current or power reading doesn't by itself tell a household anything useful. It doesn't say whether use is rising, which load is responsible, when the peak happens, or how the result compares with a similar home. People need load rankings, peak periods, cost estimates and fair comparisons, and commercial smart-controller APIs aren't always accessible for research, which is part of why this is built as a source-agnostic pipeline. The aim was to build a testable interpretation layer, not a billing system."

**Anticipate:** "Why not just use the vendor's app?" Access wasn't available for this research project, and a source-agnostic pipeline means the same analytics work regardless of which controller or meter feeds it.

---

## Slide 3: Research Aim and Objectives
**On screen:** Five objectives: (1) specify the electrical variables and dataset structure, including units and data-quality thresholds; (2) design and implement a secure pipeline that ingests, validates, stores and pre-processes readings; (3) develop eight comparative analytics algorithms for baselines, peer comparison, peak detection, ranking, anomaly warnings and estimated cost; (4) build a responsive web dashboard that presents individual and community-level insights without identifying other households; (5) evaluate accuracy, completeness, responsiveness, usability and real-data compatibility.

**Say:**
"Five objectives guided the work. First, specify the electrical variables and dataset structure the system needs, with units and data-quality thresholds. Second, build a secure pipeline that ingests, validates, stores and pre-processes the readings. Third, develop comparative analytics, in the end eight algorithms covering baselines, peer comparison, peak detection, device ranking, anomaly warnings and estimated cost. Fourth, build a responsive dashboard that presents that information at both household and community level without identifying other households. And fifth, evaluate the result against accuracy, completeness, responsiveness, usability and compatibility with real smart-meter data."

**Note:** this slide was corrected to include objective one (the data specification objective from the proposal), which the first draft of this slide had dropped. All five objectives now line up one-to-one with the five objectives in the proposal and the thesis.

---

## Slide 4: System Architecture (six layers)
**On screen:** Six-stage pipeline: Data Source (CSV/controller) to Validation (R1 to R6 checks) to Gap Handling (up to 2 intervals) to Storage (PostgreSQL) to Analytics (8 algorithms) to Dashboard (privacy-aware). Quality flags retained, short gaps imputed, audit log at each stage. Data source can be replaced without rewriting downstream layers.

**Say:**
"The pipeline has six layers, each independently testable. Data comes in from a source, here a simulated CSV matching a smart circuit controller's format, though an approved API or local gateway could replace it later without touching anything downstream. Six validation rules catch schema, timestamp, duplicate, voltage, power and physical-consistency problems. Short gaps, up to two intervals, are imputed; anything longer is left missing rather than guessed at. Everything lands in PostgreSQL with an audit log, eight algorithms turn that into energy, cost, rankings, baselines and warnings, and the dashboard presents it in a privacy-aware way."

**Anticipate:** "Why stop at two intervals for imputation?" Longer gaps are a deliberate accuracy-over-completeness trade-off: filling a multi-hour gap would be guessing, not measuring.

---

## Slide 5: Experimental Dataset and Injected Faults
**On screen:** 10 anonymised sites times 6 channels times 30 days times 96 intervals/day = 172,800 expected readings at 15-minute resolution. Injected faults: 200 duplicates, 30 invalid voltages, 10 negative-power values, 550 random losses plus a 96-reading communication gap, 30 injected abnormal-use events per dataset, hold-out dataset B. Note flags that the reported raw ingestion count (172,343) requires CSV reconciliation against the 172,800 theoretical figure.

**Say:**
"The simulated dataset covers 10 anonymised sites, 6 controller channels, 30 days at 15-minute resolution: 172,800 readings on a perfect grid. Known faults were injected under experimenter control so the ground truth is always known: 200 duplicate rows, 30 invalid voltages, 10 negative-power values, 550 randomly dropped readings, and one deliberate 96-reading communication gap. A second, independently seeded dataset with 30 abnormal-use events was held out and never used to tune anything, so it tests generalisation rather than memorisation."

**Before you present, please double-check this:** the slide's own note flags that the actual row count used for the measured ingestion run (172,343) doesn't exactly match the 172,800 theoretical grid, and says this "requires CSV reconciliation." The likely explanation is that dropped readings (550 random losses plus the 96-reading gap) remove rows from the generated CSV while injected duplicates (200) add extra rows back in, netting out close to but not exactly at 172,343. That is a plausible explanation based on the fault counts on this slide, but it has not been verified against the actual generator output in this session, so please either reconcile it from your own data generation script or have a one-line answer ready ("the gap is explained by the injected losses and duplicates; I can show the exact reconciliation if asked") rather than being caught out by it live.

---

## Slide 6: Validation and Analytics Methodology
**On screen:** Six checks (schema, timestamps, duplicates, voltage, power, physical consistency). Only short gaps (up to two intervals) are interpolated; longer gaps remain missing. Eight algorithms calculate energy, cost, peaks, ranking, baseline, comparisons, completeness and warnings. Community comparison is leave-one-out, not yet profile-matched.

**Say:**
"Validation runs six checks before anything is trusted: schema, timestamps, duplicates, voltage range, power range, and physical consistency between voltage, current and power. Only short gaps are interpolated; longer ones stay missing by design. On top of that, eight algorithms compute energy, estimated cost, peak demand, device ranking, a personal baseline, community comparison, data completeness and abnormal-use warnings. One caveat worth saying out loud: the community comparison right now is a whole-community, leave-one-out average, not yet matched to similar-usage peer groups. That's flagged as future work, not hidden."

---

## Slide 7: Data Quality and Numerical Accuracy
**On screen:** 240/240 injected invalid records detected. Mean monthly error 1.63% to 1.33% after interpolation. 19 unit tests reported as passed. Independent recomputation agreed to floating-point precision; unresolved long gaps remain a source of error.

**Say:**
"All 240 injected invalid records were correctly detected, none slipped through. Interpolating short gaps brought the mean monthly energy error down from 1.63% to 1.33%. Nineteen unit tests passed, and an independent recomputation script, written separately from the production pipeline, agreed with it to floating-point precision, meaning there's no silent miscalculation happening. The error that remains is mostly attributable to the long gaps that are deliberately left unfilled."

---

## Slide 8: Abnormal-Use Warning Trade-off
**On screen:** Hold-out dataset B. Stage 1: precision 0.49, recall 0.63. Stage 2: precision 1.00, recall 0.40. Stage 2 removed false positives but missed 18 of 30 injected events; higher precision came at the cost of lower sensitivity.

**Say:**
"This is the honest trade-off slide. On the hold-out dataset, a simple statistical rule, stage one, caught more true abnormal-use events but also raised a lot of false alerts, precision of 0.49 against recall of 0.63. Adding severity grading and a night-time rule, stage two, eliminated every false alert, precision of 1.00, but recall dropped to 0.40: it missed 18 of the 30 injected events. Neither stage is simply better. It depends whether false alerts or missed events cost more to the people using this."

**Anticipate:** "Which would you ship?" This is a tunable threshold, not a fixed choice, and user research on which error type residents tolerate better is explicitly future work.

---

## Slide 9: Dashboard and Consumption Insights
**On screen:** Site HOUSE-004 breakdown: cooking 31.4%, geyser 27.9%, plugs 21.4%. Peak use around 18:00 in the simulated profile. Resident view uses neutral status bands, not leaderboards. Live prototype dashboard screenshot.

**Say:**
"This is the resident-facing dashboard for one simulated household. Cooking, geyser and plug loads dominate its usage, and the peak sits around 18:00, a typical evening peak. One deliberate design choice: the resident view shows neutral status bands, below average, typical, above average, rather than a public numeric leaderboard, because ranking people against neighbours publicly can backfire and push already-low users upward."

---

## Slide 10: Validation with Real Smart-Meter Data
**On screen:** 10 Low Carbon London households, half-hourly whole-house readings. 14,400 valid records and 10 duplicate records identified. Monthly household totals ranged from 134.5 to 839.0 kWh. Community comparison ratios widened to 0.39 to 3.14. This confirms source compatibility, not real CBi device integration.

**Say:**
"To check this generalises beyond the simulation, the same pipeline, unmodified apart from a new whole-house channel type, was run against ten real households from the public Low Carbon London smart-meter dataset. 14,400 of the readings validated cleanly, with 10 duplicates correctly caught. Monthly totals for these real homes ranged from 134.5 to 839.0 kilowatt-hours, a much wider spread than the simulation, and the community comparison ratio widened accordingly, from the simulated 0.57 to 1.61 range out to 0.39 to 3.14 for real homes. To be precise about what this does and doesn't show: it confirms the pipeline is compatible with an independent real data source, not that it's connected to an actual CBi controller."

---

## Slide 11: Limitations and Future Work
**On screen:** Participant interpretation and SUS usability evaluation remain future work. Profile-matched peer groups are not yet implemented. Live controller integration and concurrent multi-site ingestion remain untested. A configurable per-device power factor and richer tariff models are future refinements.

**Say:**
"Being upfront about what isn't done yet: the participant-based usability study, including a System Usability Scale evaluation, is defined but not yet run. Peer comparison is whole-community, not yet matched to similar-usage profiles. Live controller integration and ingesting from multiple sites at the same time haven't been tested. And the cost model would benefit from a configurable per-device power factor and richer tariff options. None of these change what's already been demonstrated, but they're the honest boundary of this work."

---

## Slide 12: Conclusion and Future Research
**On screen:** A validated, modular dashboard translates circuit-style data into useful metrics. Controlled simulation provides known ground truth; real-data testing supports portability. Next: participant usability study, fair peer groups and richer tariff models. Further validation should use South African household data and approved live-device feeds. Thank you, Questions.

**Say:**
"To close: this is a validated, modular dashboard that turns circuit-style readings into metrics people can actually use. Controlled simulation gave known ground truth to test against, and the real-data run shows the design travels beyond the simulator it was built around. The clear next steps are the participant usability study, fairer peer-group comparisons, and richer tariff models, ideally validated against South African household data and an approved live-device feed rather than the simulation alone. Thank you, I'm happy to take questions."

---

## Likely Questions (beyond the per-slide ones above)

- **"Why simulated data instead of real controller data from the start?"** No commercial controller API access was available for this research; simulation lets fault ground truth be known exactly, and the real-data run then cross-checks that.
- **"Why eight algorithms when the proposal said six?"** The proposal set a minimum of six implemented and verified algorithms; eight were actually delivered, which exceeds rather than contradicts the proposal.
- **"Is 30 days enough?"** No, and that's an explicit limitation: it's too short for seasonal baselines and is noted as future work.
- **"What's the privacy mechanism exactly?"** Peer comparisons are pseudonymised and reported as neutral status bands rather than identifying households or ranking them publicly.
- **"Could this plug into a real CBi Astute controller?"** Not yet connected; that's the live controller integration item on the limitations slide.
- **"Why did real-data testing happen if it wasn't in the original proposal?"** It was added during the project because it substantially strengthens the claim that the architecture generalises beyond the simulator it was designed around, so it was treated as a bonus rather than skipped.

## Before You Present

- [ ] Resolve the 172,800 versus 172,343 reconciliation note on slide 5 (see that slide's note above), or have the one-line explanation ready.
- [ ] Open the deck once in PowerPoint to confirm nothing overflows on your actual machine and projector.
- [ ] Time yourself once, out loud. Twelve slides at about 1.5 minutes each is roughly 18 minutes; trim slides 2, 6 or 11 (the least numeric ones) if you're running long.
