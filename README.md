# ontobq

Ontology-as-code compiler that maps a versioned Domain document onto BigQuery
Property Graph views.

v1alpha1 loads YAML or JSON Domain documents into a typed intermediate
representation after JSON Schema validation. Mapping-view compilation,
read-only BigQuery metadata validation (`validate_bigquery_metadata`,
`OBQ101`–`OBQ105`), and data-integrity checks (`OBQ201`–`OBQ206`) are
library APIs. `validate_domain` and `build_plan` orchestrate those layers;
the `ontobq` console script exposes read-only `validate` and `plan`.
The Google Cloud adapter lives in `ontobq.bigquery.google` and is an
optional extra (`pip install ontobq[bigquery]`). Default tests use
`FakeBigQueryInspector` / `FakeBigQueryReadExecutor` and do not need a
GCP project. `apply` lands in a later issue.
Keep [RFC 8](https://github.com/yu-iskw/ontobq/issues/8) open until issue 17.

## Features

- **Package Management**: [uv](https://github.com/astral-sh/uv)
- **Build System**: [Hatchling](https://hatch.pypa.io/latest/)
- **Linting & Formatting**: [Trunk](https://trunk.io/) (Ruff, Pyright, Pylint, Bandit; Ruff is also the formatter)
- **Testing**: [pytest](https://docs.pytest.org/)
- **CI/CD**: GitHub Actions
- **Data integrity**: `compile_integrity_queries` / `validate_integrity` emit
  read-only source-table SELECTs for key nullability, uniqueness, and orphan
  endpoints (`OBQ201`–`OBQ206`). They do not query mapping views or the
  property graph. Execution goes through `BigQueryReadExecutor` (tests use
  `FakeBigQueryReadExecutor`).
- **CLI**: `ontobq validate` and `ontobq plan` are read-only. Default runs
  layers 1–4 and needs BigQuery clients; `--offline` runs load + semantics
  only and does not construct clients; `--skip-integrity` skips data scans.

## Security & Quality

This repository enforces high security and maintainability standards:

- **[GitHub CodeQL](https://codeql.github.com/)**: Deep analysis using the `security-and-quality` suite to track code health and catch vulnerabilities.
- **Complexity Guardrails**: Cyclomatic complexity is capped at **10** per function (enforced via Ruff `C901`).
- **Trunk Linters**: [Bandit](https://github.com/PyCQA/bandit) (security), [Semgrep](https://semgrep.dev/) (patterns), [Trivy](https://aquasecurity.github.io/trivy/) (IaC/Secret scanning), and [OSV-Scanner](https://github.com/google/osv-scanner) (dependencies).

## Development

Conventions, build commands, and AI-agent instructions: see [AGENTS.md](AGENTS.md). Claude Code–specific config lives in `CLAUDE.md` (it imports [AGENTS.md](AGENTS.md)) and in [`.claude/`](.claude/).

```bash
make setup-tools  # mise install --locked + mise run trunk-install
make setup        # setup-tools + Python venv (uv)
make lint         # mise run lint (Trunk)
make format       # mise run format-trunk + ssort
make test         # Run pytest test suite
make scan-vulnerabilities  # Trivy, OSV-Scanner, Grype (serial via mise)
make sbom-check   # CycloneDX SBOM generate + Trivy/Grype scan
make codeql       # Local CodeQL (x64 or Rosetta on ARM64; see AGENTS.md)
```

On Linux or macOS **ARM64**, CodeQL from `mise.lock` is an x64 bundle. `make setup-tools` skips the version check; use x64 hosts or emulation for `make codeql`.
