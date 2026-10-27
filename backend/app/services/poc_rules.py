"""Assessment catalogue. Availability describes implemented behaviour, not future promises."""
STAGES = [
    {'id':'01','name':'Baseline & AOI validation','availability':'Available','required':'Immutable baseline version, unique IDs, valid WGS84, country and exact polygon containment.','source':'Delivery Guide §§3–7'},
    {'id':'02','name':'Permitted source discovery','availability':'Connection diagnostics','required':'Approved source rights; bounded category/language/street queries; quotas, failed/capped cells, pagination where supported and provenance.','source':'Consolidated requirements §§1–2'},
    {'id':'03','name':'Category, chain & text normalization','availability':'Reference audit available','required':'Resolve missing category codes; country/language-aware profanity rules; official names, local scripts and outlet-level chain identity.','source':'Category / Chains / Profanity XLSX'},
    {'id':'04','name':'Master POI linking & deduplication','availability':'New development','required':'Stable JSAN master ID with separate provider IDs; distinguish branches and tenants; retain conflicting matches.','source':'Consolidated requirements §2'},
    {'id':'05','name':'HERE comparison','availability':'Demo only','required':'Explainable candidate signals and attribute differences; potential New/Update, no-change, verification-required and fallout; absence never implies Delete.','source':'Consolidated requirements §3; Delete Framework §3'},
    {'id':'06','name':'Street & dual-address resolution','availability':'Rules require alignment','required':'Keep primary and local slots; R1–R6, source hierarchy, ground truth and unresolved conflicts. Road classes/complex polygons still required.','source':'Street Framework §§3–7'},
    {'id':'07','name':'Evidence & closure checks','availability':'Rules require alignment','required':'Action-specific independent evidence; purpose-specific age limits; general confidence distinct from closure score; liveness blocks deletion.','source':'Evidence Workbook §§3–4; Delete Framework §§4–5'},
    {'id':'08','name':'Login, queues & allocation','availability':'New development','required':'Role/AOI/priority allocation, no duplicate claims, durable history, timestamps and idempotent comparison tasks.','source':'Consolidated requirements §4'},
    {'id':'09','name':'Attribute review & independent QC','availability':'New development','required':'Evidence-supported final values, reviewer and QC must differ, rework/reclassification/HOLD and audit history.','source':'Consolidated requirements §§5–6'},
    {'id':'10','name':'Controlled field verification','availability':'New development','required':'Specific issue, observed status, GPS accuracy, photos where permitted, verification date, unresolved values; return to independent QC.','source':'Consolidated requirements §7'},
    {'id':'11','name':'Exact Excel delivery gate','availability':'Not available','required':'Only independently approved, licensed and validated records; exact 30/39/35-column templates; no cross-file conflicts; manifest and QC summary.','source':'Delivery Guide §§6–8; Consolidated requirements §9'},
    {'id':'12','name':'Effort & quality reporting','availability':'New development','required':'Measure active handling time, QC/rework, field effort, acceptance rates and forecast assumptions; keep internal costs out of customer files.','source':'Consolidated requirements §10'},
]

CLARIFICATIONS = [
    'Deletion: score >=70 plus two independent tiers conflicts with the annotation saying any two tiers.',
    'Confidence: clarify zero score, rounding, and decimal bands on a stated 1–10 integer scale.',
    'Confidence worked example (Workbook p.6–7): its weighted values sum to 0.79 (score 8, Strong), not the stated 0.89 (9). The platform applies the formula as written.',
    'Field observations with geotagged photos are scored as street-level imagery (SLI) and count as E1 when <= 12 months old; confirm.',
    'Evidence ages differ by purpose: 3 months for full general score, 12 months for closure imagery, 24 months for street ground truth.',
    'Resolve positive closure evidence versus absence wording and the POS-only / SLI-required annotation.',
    'Street early termination and the dual-address worked example require an agreed order of evaluation.',
    'Get the complete field dictionary, current category codes, special-location guidance and supporting-file mappings.',
    'Confirm source storage, comparison, display and HERE redistribution rights separately from API access.',
]
