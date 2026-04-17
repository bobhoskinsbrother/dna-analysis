# Phase 1 — Core Pipeline

## STEP 0: Scaffolding
- [x] Create directory structure
- [x] Create pyproject.toml
- [x] Create .gitignore, .env.example
- [x] Create __init__.py files
- [x] Create tests/conftest.py
- [ ] Install dependencies

## STEP 1: Write all tests (RED)
- [ ] Unit tests: test_models, test_config, test_parser, test_policy
- [ ] Functional tests: test_db, test_loader, test_importer, test_matcher
- [ ] E2E tests: test_e2e, test_cli
- [ ] Test fixtures: sample_myheritage.csv, sample_gwas.tsv, sample_clinvar.txt

## STEP 2: Confirm RED
- [ ] Run pytest — all tests fail

## STEP 3: Implement (GREEN)
- [ ] Foundation: config.py, models.py, db.py
- [ ] Ingestion: parser.py, loader.py
- [ ] Annotation: importer.py, matcher.py
- [ ] Policy: engine.py
- [ ] CLI: cli.py

## STEP 4: Confirm GREEN
- [ ] Run pytest — all tests pass
- [ ] Coverage report
