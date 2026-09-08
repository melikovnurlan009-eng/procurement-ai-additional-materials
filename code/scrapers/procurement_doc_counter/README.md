# Procurement corpus document counter

This crawler starts from the 58 source roots in `seeds.json`, traverses child-document relationships, de-duplicates documents, and produces a frozen corpus manifest plus an auditable count.

## What counts as a document

A **document** is one unique substantive evidence item, such as an Act, statutory instrument, GOV.UK child guidance page, policy document, article, or downloadable PDF. Navigation pages, collections, organisation pages and search portals are recorded separately as containers. Individual sections of one Act are not counted as separate documents. Find a Tender is treated as a dynamic operational database and is not counted as a static document.

This definition matters: otherwise a crawler could inflate the count by treating every section URL, navigation page, search result or alternate format as a separate document.

## Run

```bash
python -m pip install -r requirements.txt
python count_documents.py --seeds seeds.json --out crawl_output
```

For a first, high-authority corpus count excluding practitioner websites:

```bash
python count_documents.py --seeds seeds.json --out crawl_official --official-only
```

## Exactness contract

`summary.json` contains `exact_count_certified`.

It is `true` only if:

1. every traversed URL was fetched successfully;
2. no root hit `--max-pages-per-root`;
3. traversal finished normally.

If any site blocks requests, times out, or the crawl is truncated, the script exits with status 2 and **does not claim the number is exact**.

## Outputs

- `summary.json`: total and grouped counts, errors, exactness flag.
- `documents.json`: one row per unique evidence document with provenance.
- `documents.csv`: spreadsheet-friendly manifest.
- `all_records.json`: evidence + containers + excluded/service/error records.
- `errors.json`: all fetch failures.

Each fetched evidence record stores source/root, canonical URL, parent URL, depth, HTTP status, content type, retrieval timestamp and SHA-256 hash.

## Traversal policy

- **legislation.gov.uk documents**: one Act/SI/selected legal document = one document; structural section links are not separately counted.
- **Changes to Legislation**: the page is a container; linked affecting instruments are discovered and counted as separate legal documents.
- **GOV.UK collections/publications/guidance**: uses the Content API where available, recursively follows child content items and attachments; collection/landing pages are containers.
- **PDF/static sources**: one file = one document.
- **Procurement Pathway / external sites**: same-domain crawl with procurement relevance filtering and a bounded depth.
- **Find a Tender**: dynamic OCDS/notice database, recorded separately rather than pretending the entire live database is one static document.
- **EUR-Lex direct legal-document roots**: one seeded legal item = one document, avoiding alternate-format double counting.

## Reproducibility recommendation

When you obtain an exact crawl, freeze the whole `crawl_output` folder with your thesis corpus version. The document count then refers to that timestamped snapshot, rather than to a changing live website.
