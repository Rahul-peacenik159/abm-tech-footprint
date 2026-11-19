# Contributing

The most useful contributions:

1. **New or better fingerprints** in an existing pack (a tool we miss, or a pattern that misfires).
2. **New industry packs** (property management, legal, fitness studios, B2B manufacturing, nonprofits...).
3. **HTTP Archive names** (`httparchive:`) for tools that don't have one yet.

## Rules for fingerprints

- Verify every pattern on at least **two real customers** of the tool with `python -m footprint discover <domain>`, and check it does **not** fire on a non-customer.
- Prefer the vendor's widget/script host over its marketing domain.
- Company-level public data only. Never add personal data, and never add sample files containing contacts.
- No patterns that require logging in, bypassing bot protection, or scraping beyond a normal page load.

## Before opening a PR

```bash
pip install -r requirements-dev.txt
python -m footprint packs          # validates all packs
python -m footprint compile-packs  # refreshes stack-packs/compiled/*.json
pytest -q
```

Describe in the PR which sites you verified the pattern on.
