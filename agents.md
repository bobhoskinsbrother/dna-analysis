# DNA Analysis — Project Description for Agentic Development

## What this project is

A local-first DNA variant interpreter that ingests a raw genotype export file from MyHeritage, annotates each variant against curated public databases, scores the strength of evidence using a deterministic policy engine, and exposes the results through a plain-English explanation layer powered by a large language model (LLM).

The system is designed so that the LLM never touches raw genetic data directly. It only receives structured, pre-scored finding objects produced by the pipeline. Every claim the LLM is allowed to make is explicitly defined in advance. Every claim it must never make is equally defined.

---

## Input file format

The user's raw genotype file is a CSV exported from MyHeritage with the following exact column headers:

```
RSID,CHROMOSOME,POSITION,RESULT
```

- **RSID** — Reference SNP identifier, e.g. `rs429358`
- **CHROMOSOME** — Chromosome number or letter, e.g. `1`, `X`
- **POSITION** — Base-pair position on the chromosome (integer)
- **RESULT** — The user's genotype at that position, e.g. `AG`, `CT`, `AA`

Lines beginning with `#` are comment lines and should be skipped. Rows where RESULT is `--`, `00`, or empty should be skipped as they represent no-calls. The file is approximately 16 MB and contains roughly 700,000 variant rows.

---

## Architecture

The system is split into five sequential layers. Each layer has a single responsibility and hands a well-defined output to the next layer.

### Layer 1 — Ingestion

Reads the raw MyHeritage CSV file, skips comment lines and no-calls, and loads the normalized variant rows into a local DuckDB database table called `sample_variants`.

**Input:** raw CSV file path  
**Output:** `sample_variants` table populated in `dna_analysis.duckdb`

### Layer 2 — Annotation store

Holds local copies of three curated public databases. These are imported once (or refreshed periodically) from downloaded files rather than queried live. The three sources are:

- **GWAS Catalog** (Genome-Wide Association Study Catalog) — published SNP-to-trait statistical associations from the NHGRI-EBI GWAS Catalog. Downloaded as a tab-separated file from https://www.ebi.ac.uk/gwas/api/search/downloads/full. Stored in the `gwas_assoc` table.
- **ClinVar** — clinical significance classifications for variants. Downloaded as `variant_summary.txt.gz` from https://ftp.ncbi.nlm.nih.gov/pub/clinvar/tab_delimited/. Stored in the `clinvar_variants` table.
- **dbSNP reference** (optional, phase 2) — used for identifier normalization and genome build resolution. Stored in `dbsnp_ref`.
- **FDA pharmacogenomic tables** (optional, phase 2) — gene-drug associations from FDA-linked sources. Stored in `pgx_refs`.

**Input:** downloaded annotation files  
**Output:** annotation tables populated in `dna_analysis.duckdb`

### Layer 3 — Matching

Joins `sample_variants` against the annotation tables on `RSID` as the primary key. Produces raw annotation records for each variant that has at least one match. Does not filter or score yet — it returns everything that matches.

**Input:** rsID from `sample_variants`  
**Output:** list of `AnnotationRecord` objects (one per catalog match)

### Layer 4 — Policy engine

The gatekeeper between raw data and the explanation layer. For each `AnnotationRecord`, the policy engine:

- Determines the **evidence type**: clinical (ClinVar), association (GWAS), or pharmacogenomic (PGx)
- Assigns a **confidence tier**: low, medium, or high, based on ClinVar review stars or GWAS p-value
- Assigns an **actionability** label: none, discuss_with_clinician, or medication_relevance
- Builds a list of **allowed claims** the LLM may make for this finding
- Builds a list of **forbidden claims** the LLM must never make for this finding
- Attaches **user_visible_notes** — caveats that must always accompany the result

The output of this layer is a `Finding` object: a complete, structured, self-contained record that fully defines what the LLM is and is not permitted to say.

**Input:** `AnnotationRecord` + user genotype  
**Output:** `Finding` object

### Layer 5 — Explanation layer (LLM)

Receives only `Finding` objects. Generates plain-English explanations and handles follow-up questions. The LLM is constrained to the contents of the `Finding` object and the system prompt rules. It may not access the raw genotype file, the annotation tables, or any external knowledge that contradicts or escalates the finding.

**Input:** `Finding` object + optional user follow-up question  
**Output:** plain-English explanation string

---

## Database schema

All data is stored in a single local DuckDB file: `dna_analysis.duckdb`

### `sample_variants`
| Column | Type | Description |
|---|---|---|
| rsid | VARCHAR (primary key) | Reference SNP identifier |
| chromosome | VARCHAR | Chromosome number or letter |
| position | BIGINT | Base-pair position |
| result | VARCHAR | User genotype e.g. AG |
| source_file | VARCHAR | Original filename |
| build_guess | VARCHAR | Genome build, default GRCh37 |
| imported_at | TIMESTAMP | When the row was loaded |

### `gwas_assoc`
| Column | Type | Description |
|---|---|---|
| id | VARCHAR (primary key) | Internal row ID |
| rsid | VARCHAR | Reference SNP identifier (indexed) |
| trait | VARCHAR | Associated trait or disease name |
| p_value | VARCHAR | Study p-value |
| odds_ratio | VARCHAR | Odds ratio where available |
| beta | VARCHAR | Beta effect size where available |
| effect_allele | VARCHAR | The allele associated with the effect |
| risk_frequency | VARCHAR | Population frequency of risk allele |
| study_accession | VARCHAR | GWAS Catalog study ID e.g. GCST000123 |
| pubmed_id | VARCHAR | PubMed publication identifier |
| mapped_gene | VARCHAR | Gene(s) near the variant |

### `clinvar_variants`
| Column | Type | Description |
|---|---|---|
| variation_id | VARCHAR (primary key) | ClinVar variation identifier |
| rsid | VARCHAR | Reference SNP identifier (indexed) |
| gene_symbol | VARCHAR | Gene symbol e.g. BRCA1 |
| condition_name | VARCHAR | Associated condition or disease |
| clinical_significance | VARCHAR | e.g. Pathogenic, Benign, VUS |
| review_status | VARCHAR | Human-readable review description |
| review_stars | INTEGER | 0–4 confidence rating |
| variation_type | VARCHAR | e.g. single nucleotide variant |

### `pgx_refs` (phase 2)
| Column | Type | Description |
|---|---|---|
| id | VARCHAR (primary key) | Internal row ID |
| gene_symbol | VARCHAR | Gene symbol |
| drug_name | VARCHAR | Drug name |
| effect_summary | VARCHAR | Plain description of gene-drug effect |
| fda_level | VARCHAR | FDA evidence level |
| rsid | VARCHAR | Representative rsID if available |

### `findings`
| Column | Type | Description |
|---|---|---|
| finding_id | VARCHAR (primary key) | UUID |
| rsid | VARCHAR | Reference SNP identifier |
| genotype | VARCHAR | User's genotype at this position |
| source_type | VARCHAR | gwas / clinvar / pgx |
| evidence_type | VARCHAR | clinical / association / pgx |
| trait_or_condition | VARCHAR | Trait or condition name |
| effect_allele | VARCHAR | Effect or risk allele |
| effect_direction | VARCHAR | increased / decreased / unclear |
| effect_size_type | VARCHAR | odds_ratio / beta / classification / none |
| effect_size_value | VARCHAR | Numeric value or label |
| clinical_significance | VARCHAR | ClinVar label if applicable |
| review_status | VARCHAR | ClinVar review status if applicable |
| confidence_tier | VARCHAR | low / medium / high |
| actionability | VARCHAR | none / discuss_with_clinician / medication_relevance |
| allowed_claims | JSON | List of claim types LLM may make |
| forbidden_claims | JSON | List of claim types LLM must never make |
| user_visible_notes | JSON | Caveats always shown with the result |
| source_refs | JSON | List of source references with type and ID |
| created_at | TIMESTAMP | When the finding was generated |

---

## Canonical Finding object

This is the JSON contract between the policy engine and the LLM. The LLM must treat this as the sole source of truth for a given result.

```json
{
  "finding_id": "uuid",
  "rsid": "rs429358",
  "genotype": "CT",
  "source_type": "gwas",
  "evidence_type": "association",
  "trait_or_condition": "Type 2 diabetes",
  "effect_allele": "T",
  "effect_direction": "increased",
  "effect_size_type": "odds_ratio",
  "effect_size_value": "1.18",
  "clinical_significance": null,
  "review_status": null,
  "confidence_tier": "medium",
  "actionability": "none",
  "allowed_claims": [
    "association_only",
    "relative_odds_description",
    "not_diagnostic",
    "modestly_increased_relative_odds"
  ],
  "forbidden_claims": [
    "diagnosis",
    "absolute_risk_estimate",
    "treatment_recommendation",
    "you_will_develop",
    "this_confirms_you_have",
    "safe_or_unsafe_label"
  ],
  "user_visible_notes": [
    "This result is a population-level statistical association, not a diagnosis.",
    "A single SNP explains only a small part of overall risk for most traits."
  ],
  "source_refs": [
    {"type": "gwas", "id": "GCST000123"},
    {"type": "pubmed", "id": "12345678"}
  ]
}
```

---

## LLM system prompt — hard rules

The following rules must be encoded in the LLM system prompt and must also be enforced by automated tests. These rules are non-negotiable and must not be softened or removed.

```
You are a genetics explanation assistant operating under strict evidence controls.

You will receive one or more structured Finding objects produced by a deterministic pipeline.
You must treat those objects as the only source of truth for any genetic claim.

HARD RULES — you must follow all of these without exception:

1. Only discuss findings that are present in the input Finding object.
   Do not infer additional variant effects or traits from your training data.

2. Do not invent rsIDs, odds ratios, confidence tiers, clinical significance labels,
   review status descriptions, or source accessions.

3. Never present a GWAS association as a diagnosis, prognosis, or deterministic prediction.
   GWAS associations are population-level statistical correlations, not individual diagnoses.

4. Never provide an absolute risk estimate (e.g. "you have a 30% chance of developing X")
   unless a specific numeric absolute risk figure is explicitly present in the Finding object.

5. Distinguish clearly between the three evidence types:
   - association: population-level GWAS statistical finding
   - clinical: curated variant-disease interpretation from ClinVar
   - pharmacogenomic: gene-drug guidance

6. If confidence_tier is "low", you must say so explicitly and frame the result
   as having limited or preliminary evidence.

7. If review_status is present and reflects a weak review (single submitter, no criteria,
   or conflicting), you must mention that the evidence is limited or contested.

8. If actionability is "none", do not suggest the user seek testing, treatment, or
   clinical follow-up based on this finding alone.

9. If actionability is "discuss_with_clinician", you may suggest the user discuss
   the finding with a clinician, especially in the context of personal or family
   history. Do not recommend specific tests or treatments.

10. If actionability is "medication_relevance", you may note that this variant may
    affect how certain medications work, and suggest the user discuss with a clinician
    or pharmacist before making any medication decisions.

11. Never use the words: confirms, proves, means you have, safe, unsafe, normal, abnormal,
    will develop, will not develop, guaranteed, or definitive — unless those exact terms
    appear in the finding's clinical_significance field from a high-confidence ClinVar record.

12. Always include at least one caveat drawn from user_visible_notes.

13. If the user asks something that would require you to go beyond the allowed_claims
    for the finding, say clearly: "The available evidence for this variant does not
    support a stronger conclusion than what has been described."

LANGUAGE TO PREFER:
- "associated with"
- "linked to in population studies"
- "may modestly increase relative odds"
- "may be protective in some studies"
- "not diagnostic on its own"
- "one small contributor to overall risk"
- "the evidence here is limited"
- "worth discussing with a clinician if relevant to your personal history"

ANSWER STRUCTURE for each finding:
1. What was found — variant, genotype, trait or condition, evidence type
2. What it may mean — one short plain-English paragraph
3. How strong the evidence is — confidence tier and why
4. What this does not mean — caveats from user_visible_notes
5. Reasonable next step — only if allowed by actionability
```

---

## Confidence tier mapping

### ClinVar review stars to confidence tier
| Stars | Review status | Confidence tier |
|---|---|---|
| 4 | Practice guideline | high |
| 3 | Reviewed by expert panel | high |
| 2 | Multiple submitters, no conflicts | medium |
| 1 | Single submitter or conflicting | low |
| 0 | No assertion criteria provided | low |

### GWAS p-value to confidence tier
| p-value | Confidence tier | Notes |
|---|---|---|
| ≤ 1×10⁻⁸ | medium | Genome-wide significance threshold — still associative, not clinical |
| ≤ 1×10⁻⁵ | low | Suggestive association only |
| > 1×10⁻⁵ | low | Weak or unreliable |

Note: GWAS associations are never assigned high confidence tier regardless of p-value,
because statistical association is fundamentally different from clinical interpretation.

---

## Actionability rules

| Actionability | When assigned | What LLM may say |
|---|---|---|
| none | GWAS findings; benign or VUS ClinVar; no clinical flag | Informational only. No follow-up action suggested. |
| discuss_with_clinician | Pathogenic or likely pathogenic ClinVar; drug response label | May suggest discussing with a clinician in context of personal history. |
| medication_relevance | PGx source type | May note potential drug-response relevance. Suggest pharmacist or clinician discussion. |

---

## Claim vocabulary

### Allowed claim types and their meanings
| Claim type | Meaning |
|---|---|
| association_only | This is a statistical association from a population study |
| relative_odds_description | The LLM may describe the odds ratio or direction |
| not_diagnostic | The LLM must state this is not a diagnosis |
| modestly_increased_relative_odds | Odds ratio > 1, LLM may describe as modest increase |
| possibly_protective_association | Odds ratio < 1, LLM may describe as possibly protective |
| clinical_interpretation_summary | LLM may summarise the ClinVar clinical significance |
| review_status_description | LLM may explain what the review status means |

### Forbidden claim types and their meanings
| Claim type | Meaning |
|---|---|
| diagnosis | LLM must not diagnose the user |
| absolute_risk_estimate | LLM must not give a percentage chance |
| treatment_recommendation | LLM must not recommend specific treatments |
| you_will_develop | LLM must not say the user will develop a condition |
| this_confirms_you_have | LLM must not confirm the user has a condition |
| safe_or_unsafe_label | LLM must not label anything as safe or unsafe |
| strong_clinical_assertion | LLM must not make strong clinical claims for low-confidence ClinVar records |

---

## Technology stack

| Component | Choice | Reason |
|---|---|---|
| Language | Python 3.11+ | Strong bioinformatics ecosystem, familiar to the team |
| Local database | DuckDB | In-process analytical database, no server, fast on large CSV/Parquet files |
| Data validation | Pydantic v2 | Strict canonical models, fast serialization |
| CLI | Typer | Clean command-line interface built on Python type hints |
| Terminal output | Rich | Formatted tables and progress output in the terminal |
| HTTP client | httpx | Async-capable HTTP for any future API calls |
| LLM client | openai Python SDK | Compatible with OpenAI and OpenAI-compatible local endpoints (e.g. Ollama) |
| Testing | pytest + pytest-cov | Unit and integration tests with coverage |
| Linting | Ruff | Fast Python linter and formatter |

---

## Project folder structure

```
dna-analysis/
├── pyproject.toml              # Project metadata and dependencies
├── .env.example                # Environment variable template
├── .gitignore                  # Excludes raw DNA files and secrets
├── agents.md                   # This file — project description for agentic development
├── dna_analysis.duckdb         # Local database (created at runtime, not in source control)
│
├── data/
│   ├── raw/                    # Raw MyHeritage export files (git-ignored)
│   └── curated/                # Downloaded annotation files (git-ignored)
│
├── app/
│   ├── config.py               # Central config loaded from environment variables
│   ├── models.py               # Pydantic canonical models (SampleVariant, Finding, etc.)
│   ├── db.py                   # DuckDB connection and schema initialisation
│   ├── cli.py                  # Typer command-line interface
│   │
│   ├── ingest/
│   │   ├── parser.py           # MyHeritage CSV parser
│   │   └── loader.py           # Batch loader into sample_variants table
│   │
│   ├── annotate/
│   │   ├── importer.py         # GWAS Catalog and ClinVar importers
│   │   └── matcher.py          # rsID-based matcher against annotation tables
│   │
│   ├── policy/
│   │   └── engine.py           # Converts AnnotationRecord + genotype into Finding
│   │
│   └── explain/
│       ├── prompt.py           # System prompt builder and LLM client
│       └── contract.py         # Prompt contract constants and forbidden phrase list
│
└── tests/
    ├── test_parser.py          # Parser unit tests
    ├── test_policy.py          # Policy engine unit tests — confidence, actionability, claims
    ├── test_prompt_rules.py    # LLM guardrail tests — forbidden phrases, claim escalation
    └── fixtures/
        └── sample_variants.csv # Small synthetic test fixture (not real DNA data)
```

---

## CLI commands (planned)

```
dna init-db                         # Initialise the local DuckDB schema
dna load <file>                     # Load a raw MyHeritage CSV into sample_variants
dna import-gwas <file>              # Import GWAS Catalog associations TSV
dna import-clinvar <file>           # Import ClinVar variant_summary.txt
dna match <rsid>                    # Match a single rsID against annotation tables
dna findings                        # List all findings in the database
dna explain <finding_id>            # Generate plain-English explanation for a finding
dna ask <finding_id> "<question>"   # Ask a follow-up question about a specific finding
dna run-all <file>                  # Load, match, score, and generate findings for all variants
```

---

## Phased implementation plan

### Phase 1 — Core pipeline (build first)

- Implement `app/ingest/parser.py` — MyHeritage CSV parser
- Implement `app/ingest/loader.py` — batch loader into DuckDB
- Implement `app/db.py` — schema initialisation
- Implement `app/annotate/importer.py` — GWAS Catalog and ClinVar importers
- Implement `app/annotate/matcher.py` — rsID-based matching
- Implement `app/policy/engine.py` — confidence, actionability, and claim building
- Implement `app/cli.py` — init-db, load, import-gwas, import-clinvar, match, findings commands
- Write `tests/test_parser.py` and `tests/test_policy.py`
- Validate end-to-end with a small set of known rsIDs before touching the LLM layer

### Phase 2 — LLM explanation layer (build after phase 1 passes tests)

- Implement `app/explain/contract.py` — encode the hard rules and forbidden phrases as constants
- Implement `app/explain/prompt.py` — system prompt builder and OpenAI client
- Add `dna explain` and `dna ask` CLI commands
- Write `tests/test_prompt_rules.py` — automated checks that the system prompt does not
  allow forbidden phrases and does not escalate claims beyond what the finding permits

### Phase 3 — Enhancements (optional, after phase 2)

- Add PGx support using FDA pharmacogenomic tables
- Add genome build awareness and optional liftover
- Add allele harmonisation for strand ambiguity
- Add a simple local web UI (FastAPI + static HTML) for browsing findings
- Add batch explain mode for all findings above a confidence threshold

---

## Key design invariants

These must never be violated regardless of future changes:

1. The LLM must never receive the raw genotype file as input.
2. The LLM must only receive `Finding` objects produced by the policy engine.
3. The policy engine must assign `allowed_claims` and `forbidden_claims` to every finding before it reaches the LLM.
4. GWAS associations must never be assigned high confidence tier.
5. Absolute risk estimates must never be generated unless explicitly present in the Finding object with a sourced numeric value.
6. The forbidden claims list must be encoded as constants in `app/explain/contract.py` and tested in `tests/test_prompt_rules.py`.
