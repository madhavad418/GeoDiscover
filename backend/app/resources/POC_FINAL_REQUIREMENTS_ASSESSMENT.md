# JSAN POC operations assessment — 27 October 2026

This assessment implements the requested assessment-first step in the consolidated requirements. Submission target: **13 November 2026**, 17 calendar days from this review. This is a delivery plan, not a completion guarantee. The complete source-to-independent-QC-to-exact-XLSX workflow is not yet implemented.

## Package review

All 20 files were inventoried with SHA-256 hashes in `backend/app/resources/poc_audit.json`: four PDFs (49 pages of extracted text), seven XLSX workbooks, three CSV baselines, three GeoJSON boundaries and three QGIS metadata files. The spreadsheet audit scans every populated row, distinguishes formatting-only rows, and reports formula errors. Boundary containment uses WGS84 geometries, including polygon edges. Embedded PDF diagrams have not been independently visually verified in this review.

| AOI | Records | Unique IDs | Outside supplied boundary | Codes absent from supplied mapping sheets |
| --- | ---: | ---: | ---: | ---: |
| Divisoria | 3,636 | 3,636 | 0 | 170 |
| Kampung Bali | 6,174 | 6,174 | 0 | 82 |
| Thanon Phaya Thai | 8,351 | 8,351 | 0 | 410 |

The three boundary geometries are valid; all display coordinates are valid; IDs are unique across files; names and primary categories are populated. This does not establish current business existence or address accuracy. Two extract filenames understate their parsed row counts by one. There is no explicit last-verified-date field; `version` is not evidence of verification.

Category metadata contains 412 `#REF!` cells on the Category sheet. Unioning populated PDS Category Code columns across mapping sheets yields 397 distinct codes; 662 baseline records use codes absent from that union. Treat these as reference-version gaps requiring clarification, not proof that HERE's POIs are invalid. Chain metadata has 55,123 populated records; profanity metadata has 10,837; the parent-child example has 614. Chain metadata lacks a chain-ID column, so it cannot by itself populate authoritative chain IDs. Apply profanity rules using country/language and whole-name flags, not naive substring deletion.

Delivery templates are empty data tables with formatting-only trailing rows/columns:

| Action | Sheet | Controlled headers |
| --- | --- | ---: |
| New | `sheet1` | 30 |
| Update | `update` | 39 |
| Delete | `Sheet1` | 35 |

Keep exact header spelling, order and sheet names. Do not copy metadata dimensions as output row counts. The independent field dictionary, POC Introduction V2.1, complete special-location guidance, agreed manifest/checklist, and authoritative category update are not present in this package.

## Module-wise availability and work required

| Module | Available in this checkout | Required work / dependencies |
| --- | --- | --- |
| AOI/baseline | React/MapLibre viewer; CSV/XLSX import; PostGIS point storage; browse/search/filter | Persist/version boundary uploads; verify selected boundary per run; extend operational validations |
| Compare | Explicitly simulated Google/Grab/Apple proposals and simple review persistence | Production candidate generation, ambiguity handling, rule versions, full attribute comparisons; demo output must never become customer delivery |
| Source collection | Server configuration now supplied for Google Places and AWS Grab index | Validate credentials, endpoint/version, coverage and contractual usage; approved source adapters, pagination/checkpoints, quotas, throttling, idempotency and provenance |
| Identity linking | Basic normalized-name/category/distance helper | Master JSAN IDs; source-reference namespaces; outlet identity; phone/domain/unit signals; competing matches; preserve local scripts |
| Review | Demo approve/reject controls | Attribute-level corrections and evidence, verification date, reason codes, change history, HOLD/FIELD REVIEW, supporting inputs |
| Login/allocation | Not present | Role-based authentication; queues; transaction-safe allocation (`FOR UPDATE SKIP LOCKED`); workload/priority/AOI eligibility; idempotent task keys |
| Independent QC | Not present | Reviewer and QC identities must differ; NEW/UPDATE/DELETE/fallout/rework queues; rejection/reclassification/field escalation and history |
| Field verification | Map navigation/reference links | Controlled POC field form with issue, status, GPS accuracy, timestamp, evidence, unresolved values; return to independent QC |
| Delivery | Demo CSV export only | Exact customer XLSX templates; approved-only frozen snapshot; attribute lineage and source rights; QC summary, reconciliation and manifest |
| Operations metrics | Baseline counts | Activity timestamps and event log; cycle time vs active handling time; productivity, rework, cost assumptions, accepted-unit costs and uncertainty |
| POI Management / POI Express | No separate codebase supplied or identified | Obtain repo/API/schema access before claiming reuse; do not invent existing capabilities |

## Source integration assessment

**Google Places:** use official Places API New with field masks and bounded requests. Standard policies restrict persistence of Places content; place IDs have a storage exception. Results on a map require a Google map; non-map display needs proper attribution. Credentials do not establish permission to build or enrich a redistributable HERE dataset. Default implementation is a diagnostic/reference connection, not a bulk-harvest/export feed. Obtain explicit applicable rights before ingestion, comparison or export of restricted attributes.

**AWS GrabMaps:** configured index `explore.place.Grab`, region `ap-southeast-1`, API-key authentication. This is a named Places v1 index, so use `SearchPlaceIndexForText` rather than silently treating the index as Places v2. V1 text search has a bounded result set and no next-page-token parameter; do not invent pagination. Provider documentation currently differs on V2 Grab readiness; validate the actual account/product before migration. Storage/use/redistribution permissions are separate from successful requests. V2's `IntendedUse=Storage` does not by itself establish the right to redistribute to HERE. Default diagnostics retain no provider POI payload.

**Apple Maps:** no configured access identified. Standard Developer Program terms restrict bulk extraction, derivative databases and use to improve another mapping service. Show unavailable pending credentials and explicit appropriate permission. Do not implement a fake active Apple connector or substitute an unofficial scraping API.

**Other sources:** independently licensed datasets, permitted official websites/directories and field observations can provide deliverable evidence. Capture the license scope and actual provenance of each attribute. Do not relabel provider-derived content as independent field evidence.

## Post-processing stages and gates

1. **Freeze input versions:** AOI, baseline, reference tables, rules and templates; keep original hashes and stable source IDs. Validate schema and encoding. Preserve source observations separately from the customer baseline.
2. **Bounded discovery:** AOI-aware query plan by category, language and street/market; explicit request ceiling, per-provider quotas, duplicate requests, failed/capped cells and retry/checkpoint state. A successful search is not exhaustive coverage. Search boundary-crossing cells as needed but clip accepted display points to the polygon.
3. **Normalize and validate:** Unicode/local names, transliteration as a separate field, country-specific phones, domain/branch URLs, units/admin hierarchy, valid coordinates and freshness. No invented values. Map provider taxonomies to supplied HERE codes through a versioned crosswalk; unresolved mappings require review.
4. **Link identities:** source-ID uniqueness within provider; one master business with multiple references; avoid merging shared coordinates, chain branches or mall tenants. Store candidate scores, supporting and contradicting signals, alternatives and rejected links. A website brand domain alone does not distinguish branches.
5. **Match HERE:** evaluate 0–50 m, 50–250 m, 250–1,000 m bands and identity-led relocation. The draft closure spec's identity rule is name similarity >=0.85 plus a phone/address/domain identity signal, with unit-level safeguards. Preserve multiple plausible matches as FALLOUT REVIEW. Store exact metric/version and explain each suggested change.
6. **Classify provisionally:** matched identical -> NO CHANGE; same identity with supported difference -> POTENTIAL UPDATE; unmatched external -> POTENTIAL NEW pending verification; missing external counterpart -> VERIFICATION REQUIRED; confirmed invalidity/closure evidence -> POTENTIAL DELETE; conflicts -> FALLOUT REVIEW. Never convert absence alone into DELETE.
7. **Resolve addresses:** primary road-level and local unit-level slots. R1–R6 dual-address rules, T1 ground-truth override, weighted supporting sources, spatial checks and escalation. Preserve valid dual addresses. Road classes and complex polygons are additional inputs; do not infer them from AOI boundaries. Adapt Indonesian normalization for Thai/Philippine contexts.
8. **Assess evidence:** enforce action-specific completeness first. Proposed general weights: imagery/POS/official website/official social each 20%, competitor/third-party 15%, other imagery 5%. Retain item-level rubric score, observation and retrieval dates, identity, independence, ownership/licensing and source URL. Score is advisory, not approval.
9. **Deletion safeguards:** apply D1–D7 in order: retain, geometry correction, review/update, relocation, then evidence-supported closure; otherwise pending validation. E1 override or proposed weighted score >=70 from >=2 independent tiers. Active liveness of equal/higher authority blocks deletion. Link successor/predecessor for supersession. Separate duplicate/nonexistent reason proof from closure proof.
10. **Task allocation:** idempotency key includes project/record/work type/input revision. Atomic claim by eligible role/AOI; no double assignment; keep in-progress tasks; supervisor reassignment requires audit. Record assignment/start/pause/completion/rework times.
11. **Review and independent QC:** attribute-level evidence and final proposed values; business status, date, reason and unresolved questions. QC analyst cannot equal initial reviewer. Field results return to independent QC. Approval does not bypass source rights or required evidence.
12. **Delivery preflight:** mandatory fields, HERE/stable supplier IDs, category crosswalk, duplicate/cross-action conflicts, country/admin/address consistency, WGS84 display/routing plausibility, AOI containment, last verification, relationships, text/profanity, evidence and permission, independent QC. Block unresolved Blockers; fix/disclose Major issues under the guide.
13. **Frozen export:** exact three XLSX templates; preserve sheets/headers and required filenames, no macros/external links/hidden sheets. Guard formula injection in user-supplied text. Reopen workbooks and reconcile counts. Generate manifest, QC checklist, category mapping, reconciliation and limitations. Internal productivity details stay out of customer files.
14. **Measure performance:** unique master POIs vs source observations; confirmed/possible matches; proposed vs approved actions; queue statuses; active handling duration vs wall time; independent QC pass/rework rate. Forecast remaining work using measured rates and explicit staffing/cost assumptions, never simulated metrics.

## Unresolved rules requiring written alignment

- Closure rule >=70 with two independent tiers versus annotation saying any two tiers.
- General scoring workbook's absence language versus closure specification's positive proof requirement.
- E1 imagery/POS override and annotation requiring SLI: confirm evidence minimum for POS-only cases.
- Different imagery ages (3 months full general score, 12 months closure, 24 months street GT) must remain purpose-specific.
- General confidence formula produces zero while labels say 1–10; decimal band thresholds conflict with whole-number rounding.
- Street early-termination instructions conflict with the worked example's preservation of both valid address slots; source-count annotations need precedence.
- Non-existence, duplicates and relocation deletion semantics in delivery guide versus closure-focused framework.
- Internal audit/relationship/source fields exceed supplied export template columns; agree supporting-file mappings, not ad hoc new headers.

## Proposed data model

Reuse `customer_datasets` and `customer_pois` as immutable baseline versions. Add `aoi_versions`, `source_contracts`, `discovery_runs`, `discovery_queries`, `source_observations`, `master_pois`, `poi_source_links`, `match_runs`, `match_candidates`, `attribute_proposals`, `evidence_items`, `tasks`, `task_assignments`, `review_decisions`, `qc_decisions`, `field_observations`, `audit_events`, `delivery_snapshots`, `delivery_files` and `activity_sessions`. Separate provider-restricted references from deliverable records. Store dates, permitted use, rule version and provenance on every observation/decision; keep PostGIS geometry for authorized spatial records. Preflight reports can persist independently without copying provider content.

## P0 acceptance tests

- All 18,161 baseline rows reconcile to source, zero duplicate IDs, all supplied display points inside the exact polygon; altered upload outside the polygon is flagged.
- Provider calls use correct bounds, country, field masks and auth; missing/invalid keys, 403, 429, timeouts and malformed responses are visible without secret leakage. Capped/failed searches never display complete coverage.
- Repeat source IDs are idempotent; nearby chain branches and separate mall tenants stay separate; one physical outlet across multiple permitted sources links to one master.
- Spelling/coordinate differences do not independently create new/deleted POIs; contradictory evidence routes to fallout. Provider absence never deletes.
- Concurrent task claims cannot assign the same task twice; rerunning unchanged comparisons does not duplicate tasks; reviewer cannot QC own record.
- Missing evidence blocks submission; liveness blocks deletion; incomplete field review returns to QC/HOLD rather than approval.
- Only eligible independently approved records enter exact-template XLSX files; templates retain case-sensitive sheet names/headers; counts and manifest reconcile and unsafe spreadsheet text is escaped.
- Audit captures before/after, actor, date, reason and rules. Role/access tests prevent unauthorized review, reassignment, export and paid API use.
- Coverage/accuracy is evaluated against independently verified ground truth, not just imported counts. Guide targets: 90% combined coverage; <=5% extras/closed; 95% name/category, structured address and display/routing accuracy; verification date on every delivered record.

## Delivery sequence and risks

- **27–29 October:** approve rule precedence and data rights; confirm fields/category reference; validate real source access; audit package; obtain other project code and define smallest end-to-end pilot.
- **30 October–3 November:** approved-source ingestion and linking; comparison explanations; login/queues/allocation; reviewer and independent QC on a representative batch.
- **4–8 November:** evidence and field return path; exact exports and acceptance tests; extend to remaining AOIs; collect actual handling-time metrics.
- **9–11 November:** complete remaining verification, rework and independent QC; check coverage and licensing; freeze templates/data versions.
- **12–13 November:** final gate, manifest and reconciliation; submit agreed package.

Risks: source contracts and incomplete API coverage; reference/schema contradictions; no separate POI Management/Express access; staffing for review/QC and field work; missing road/complex data; development/testing time. Establish achievable area/category scope and capacity with the team immediately; do not promise full 18,161-record verification from API availability alone.

## Current implementation boundary

The new POC Operations tab provides the package assessment, live baseline preflight, provider configuration/connection diagnostics and required post-processing stages. It is not a claim that authenticated task allocation, full multi-source discovery, independent QC or exact customer delivery are finished. Standard provider references stay outside customer export. Unavailable integrations and incomplete stages must remain explicit.

## References

Local package: Supplier Delivery Guide v1.2 (pp. 2–7), Evidence Weighting Workbook (pp. 3–10), Delete Framework v1.0 (pp. 4–10), Street Name Framework v1.1 (pp. 4–14), all seven XLSX files and three AOI/extract pairs. Consolidated requirements supplied 27 October 2026 are the functional scope.

- [Google Places policies](https://developers.google.com/maps/documentation/places/web-service/policies)
- [Google Text Search New](https://developers.google.com/maps/documentation/places/web-service/text-search)
- [AWS GrabMaps coverage](https://docs.aws.amazon.com/location/latest/developerguide/GrabMaps.html)
- [AWS named-index text search](https://docs.aws.amazon.com/location/previous/APIReference/API_SearchPlaceIndexForText.html)
- [AWS Places V2 intended use](https://docs.aws.amazon.com/location/latest/developerguide/places-intended-use.html)
- [Apple Maps Server API search](https://developer.apple.com/documentation/applemapsserverapi/-v1-search)
- [Apple Developer agreement, Attachment 6](https://developer.apple.com/support/terms/apple-developer-program-license-agreement/)
