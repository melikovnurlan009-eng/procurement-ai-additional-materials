#!/usr/bin/env python3
"""
Procurement corpus crawler with relevance-aware traversal.

Core rule:
    Reachable != relevant.

Every discovered URL is assigned:
    - a relationship to its parent, and
    - a corpus class: CORE, OFFICIAL_SUPPORT, LEGAL_DEPENDENCY,
      SECONDARY, DISCOVERY_ONLY, EXCLUDE, or OPERATIONAL_SERVICE.

Only trusted relationships are allowed to propagate traversal. Generic GOV.UK
"related content" does not recursively expand the corpus.
"""

import argparse
import csv
import hashlib
import json
import re
import sys
import time
from collections import Counter, deque
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

USER_AGENT = "ProcurementThesisCorpusCounter/2.0 (+academic research; relevance-aware reproducible crawl)"
TRACKING_KEYS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "gclid", "fbclid"
}
DOC_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".odt", ".rtf", ".xls", ".xlsx", ".csv",
    ".ppt", ".pptx", ".txt", ".xml"
}

# These are intentionally procurement-specific. Very broad terms such as
# "public sector" and "competition" are not enough by themselves.
PROCUREMENT_TERMS = {
    "procurement", "public procurement", "government procurement",
    "procurement act", "procurement regulations", "procurement policy note",
    "ppn", "tender", "tendering", "contracting authority", "public contract",
    "covered procurement", "contract award", "award criteria", "direct award",
    "framework", "open framework", "dynamic market", "supplier", "exclusion",
    "excluded supplier", "excludable supplier", "debarment", "standstill",
    "transparency notice", "tender notice", "contract award notice",
    "contract details notice", "contract change notice", "contract modification",
    "procurement review unit", "commercial playbook", "sourcing playbook",
    "construction playbook", "social value", "bid rigging"
}

# Stronger terms for treaty filtering. A treaty is not useful merely because it
# is an international agreement.
TRADE_PROCUREMENT_TERMS = {
    "government procurement", "public procurement", "procurement chapter",
    "government procurement chapter", "covered entities", "covered entity",
    "procurement thresholds", "procurement threshold", "wto gpa",
    "agreement on government procurement", "treaty state supplier"
}

# Build UK root is deliberately narrow: the selected source was CAS, not the
# entire Build UK information library.
CAS_TERMS = {
    "common assessment standard", "common-assessment-standard",
    "cas question set", "building safety section"
}

CMA_TERMS = {
    "bid rigging", "public procurement", "procurement", "cartel", "collusion",
    "tendering"
}

# Relations that describe navigation/taxonomy rather than evidence dependency.
GOVUK_NAV_RELATIONS = {
    "organisations", "primary_publishing_organisation", "taxons",
    "mainstream_browse_pages", "topics", "parent", "parents",
    "related", "related_items", "ordered_related_items", "world_locations",
    "roles", "people"
}

# Content API relations that may represent direct child/substantive content.
# Even these are still subjected to root-specific relevance checks.
GOVUK_CHILD_RELATIONS = {
    "children", "documents", "parts", "subpages", "associated",
    "supporting_documents"
}

GOVUK_CONTAINER_TYPES = {
    "collection", "organisation", "topic", "taxon", "mainstream_browse_page"
}

CORPUS_CLASSES = {
    "CORE", "OFFICIAL_SUPPORT", "LEGAL_DEPENDENCY", "SECONDARY",
    "DISCOVERY_ONLY", "EXCLUDE", "OPERATIONAL_SERVICE"
}

EVIDENCE_CLASSES = {"CORE", "OFFICIAL_SUPPORT", "LEGAL_DEPENDENCY", "SECONDARY"}


@dataclass
class Record:
    url: str
    canonical_url: str
    root_url: str
    root_name: str
    group_id: str
    depth: int
    parent_url: Optional[str]
    relationship: str = "SEED"
    status_code: Optional[int] = None
    content_type: Optional[str] = None
    title: Optional[str] = None
    kind: str = "unknown"  # evidence | container | operational_service | excluded | error
    corpus_class: str = "EXCLUDE"
    relevant: Optional[bool] = None
    reason: Optional[str] = None
    sha256: Optional[str] = None
    fetched_at: Optional[str] = None
    final_url: Optional[str] = None
    content_id: Optional[str] = None
    govuk_document_type: Optional[str] = None
    govuk_content_purpose: Optional[str] = None
    children_found: int = 0


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonicalize(url: str) -> str:
    p = urlparse(url)
    scheme = (p.scheme or "https").lower()
    netloc = p.netloc.lower()
    path = re.sub(r"/{2,}", "/", p.path or "/")
    if path != "/" and path.endswith("/"):
        path = path[:-1]
    query_pairs = []
    for k, v in parse_qsl(p.query, keep_blank_values=True):
        if k.lower() not in TRACKING_KEYS:
            query_pairs.append((k, v))
    query = urlencode(sorted(query_pairs))
    return urlunparse((scheme, netloc, path, "", query, ""))


def suffix(url: str) -> str:
    path = urlparse(url).path.lower()
    for ext in DOC_EXTENSIONS:
        if path.endswith(ext):
            return ext
    return ""


def hostname(url: str) -> str:
    return urlparse(url).netloc.lower()


def govuk_api_url(url: str) -> Optional[str]:
    p = urlparse(url)
    if p.netloc.lower() not in {"www.gov.uk", "gov.uk"}:
        return None
    if p.path.startswith("/api/content/"):
        return url
    return "https://www.gov.uk/api/content" + p.path


def normalise_text(text: str) -> str:
    return " ".join((text or "").lower().split())


def has_any(text: str, terms: Set[str]) -> bool:
    t = normalise_text(text)
    return any(term in t for term in terms)


def procurement_relevant(text: str) -> bool:
    return has_any(text, PROCUREMENT_TERMS)


def trade_procurement_relevant(text: str) -> bool:
    return has_any(text, TRADE_PROCUREMENT_TERMS)


def looks_like_non_document(url: str) -> bool:
    path = urlparse(url).path.lower()
    bad = [
        "/search", "/contact", "/people/", "/careers", "/events", "/privacy",
        "/cookies", "/accessibility", "/sitemap", "/login", "/sign-in",
        "/subscribe", "/author/", "/tag/", "/about-us", "/offices/"
    ]
    return any(x in path for x in bad)


def details_to_text(details) -> str:
    """Flatten useful Content API details into text for relevance tests."""
    chunks: List[str] = []

    def walk(x):
        if isinstance(x, str):
            chunks.append(x)
        elif isinstance(x, dict):
            for k, v in x.items():
                # Avoid ingesting raw binary-ish or huge metadata fields if present.
                if k.lower() in {"image", "image_url", "api_url"}:
                    continue
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    walk(details)
    return " ".join(chunks)


def seed_corpus_class(group_id: str, root_name: str, url: str) -> str:
    if group_id == "LEGISLATION_GOV_UK_DOCUMENT":
        return "CORE"
    if group_id == "LEGISLATION_GOV_UK_CHANGES":
        return "DISCOVERY_ONLY"
    if group_id in {"GOVUK_COLLECTION", "GOVUK_ORGANISATION"}:
        return "DISCOVERY_ONLY"
    if group_id in {"GOVUK_PUBLICATION", "GOVUK_GUIDANCE", "DIRECT_PDF", "CPS_GUIDANCE"}:
        return "OFFICIAL_SUPPORT"
    if group_id == "PROCUREMENT_PATHWAY":
        if url.rstrip("/") == "https://www.procurementpathway.civilservice.gov.uk":
            return "DISCOVERY_ONLY"
        return "OFFICIAL_SUPPORT"
    if group_id == "FIND_TENDER":
        return "OPERATIONAL_SERVICE"
    if group_id == "EUR_LEX":
        return "LEGAL_DEPENDENCY"
    if group_id == "GENERIC_EXTERNAL_HTML":
        # Selected article/resource roots are secondary; broad homepages are discovery-only.
        path = urlparse(url).path.strip("/")
        if root_name == "Build UK - Common Assessment Standard":
            return "SECONDARY"
        if path and path not in {"resources"}:
            return "SECONDARY"
        return "DISCOVERY_ONLY"
    return "SECONDARY"


def kind_for_class(corpus_class: str) -> str:
    if corpus_class in EVIDENCE_CLASSES:
        return "evidence"
    if corpus_class == "OPERATIONAL_SERVICE":
        return "operational_service"
    if corpus_class == "DISCOVERY_ONLY":
        return "container"
    return "excluded"


class Crawler:
    def __init__(self, timeout=25, delay=0.15, max_depth=4, max_pages_per_root=5000, include_external=True):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/json,application/pdf,*/*;q=0.8"
        })
        self.timeout = timeout
        self.delay = delay
        self.max_depth = max_depth
        self.max_pages_per_root = max_pages_per_root
        self.include_external = include_external
        self.records: Dict[str, Record] = {}
        self.errors: List[dict] = []
        self.truncated_roots: Set[str] = set()
        self.visited_fetch: Set[str] = set()

    def fetch(self, url: str) -> requests.Response:
        if self.delay:
            time.sleep(self.delay)
        return self.session.get(url, timeout=self.timeout, allow_redirects=True)

    def _put_record(self, rec: Record) -> Record:
        old = self.records.get(rec.canonical_url)
        if old is None:
            self.records[rec.canonical_url] = rec
            return rec
        # Prefer a stronger evidence classification and shallower provenance.
        priority = {
            "CORE": 6, "LEGAL_DEPENDENCY": 5, "OFFICIAL_SUPPORT": 4,
            "SECONDARY": 3, "DISCOVERY_ONLY": 2, "EXCLUDE": 1,
            "OPERATIONAL_SERVICE": 0
        }
        if priority.get(rec.corpus_class, 0) > priority.get(old.corpus_class, 0):
            old.corpus_class = rec.corpus_class
            old.kind = kind_for_class(rec.corpus_class)
            old.reason = rec.reason
            old.relationship = rec.relationship
            old.relevant = rec.relevant
        if rec.depth < old.depth:
            old.depth = rec.depth
            old.parent_url = rec.parent_url
            old.relationship = rec.relationship
        return old

    def crawl_root(self, root: dict, group_id: str):
        root_url = canonicalize(root["url"])
        root_name = root["name"]
        seed_class = seed_corpus_class(group_id, root_name, root_url)

        if group_id == "GENERIC_EXTERNAL_HTML" and not self.include_external:
            rec = Record(
                url=root_url, canonical_url=root_url, root_url=root_url,
                root_name=root_name, group_id=group_id, depth=0, parent_url=None,
                relationship="SEED", kind="excluded", corpus_class="EXCLUDE",
                relevant=False, reason="external crawling disabled"
            )
            self.records[root_url] = rec
            return

        if group_id == "FIND_TENDER":
            rec = Record(
                url=root_url, canonical_url=root_url, root_url=root_url,
                root_name=root_name, group_id=group_id, depth=0, parent_url=None,
                relationship="SEED", kind="operational_service",
                corpus_class="OPERATIONAL_SERVICE", relevant=True,
                reason="dynamic procurement database; tracked separately from static documents"
            )
            self.records[root_url] = rec
            return

        if group_id.startswith("GOVUK_"):
            self._crawl_govuk(root_url, root_name, group_id)
        elif group_id == "LEGISLATION_GOV_UK_CHANGES":
            self._crawl_changes(root_url, root_name, group_id)
        elif group_id == "GENERIC_EXTERNAL_HTML":
            self._crawl_generic(root_url, root_name, group_id)
        elif group_id == "PROCUREMENT_PATHWAY" and seed_class == "DISCOVERY_ONLY":
            self._crawl_generic(root_url, root_name, group_id, force_procurement_site=True)
        else:
            self._fetch_leaf(
                root_url, root_url, root_name, group_id, 0, None, "SEED",
                seed_class, "explicit curated seed"
            )

    def _save_response(self, rec: Record, resp: requests.Response):
        rec.status_code = resp.status_code
        rec.final_url = canonicalize(resp.url)
        rec.content_type = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
        rec.fetched_at = utc_now()
        rec.sha256 = hashlib.sha256(resp.content).hexdigest()
        if "html" in (rec.content_type or ""):
            try:
                soup = BeautifulSoup(resp.content, "lxml")
                if soup.title:
                    rec.title = soup.title.get_text(" ", strip=True)
                h1 = soup.find("h1")
                if h1:
                    rec.title = h1.get_text(" ", strip=True)
            except Exception:
                pass

    def _fetch_leaf(self, url: str, root_url: str, root_name: str, group_id: str,
                    depth: int, parent: Optional[str], relationship: str,
                    corpus_class: str, reason: str):
        cu = canonicalize(url)
        rec = Record(
            url=url, canonical_url=cu, root_url=root_url, root_name=root_name,
            group_id=group_id, depth=depth, parent_url=parent,
            relationship=relationship, corpus_class=corpus_class,
            kind=kind_for_class(corpus_class), relevant=corpus_class in EVIDENCE_CLASSES,
            reason=reason
        )
        rec = self._put_record(rec)
        if cu in self.visited_fetch:
            return
        self.visited_fetch.add(cu)
        try:
            resp = self.fetch(url)
            self._save_response(rec, resp)
            if resp.status_code >= 400:
                rec.kind = "error"
                rec.reason = f"HTTP {resp.status_code}"
                self.errors.append({"url": url, "error": rec.reason})
        except Exception as e:
            rec.kind = "error"
            rec.reason = repr(e)
            rec.fetched_at = utc_now()
            self.errors.append({"url": url, "error": repr(e)})

    # ---------- GOV.UK relevance policy ----------

    def _govuk_root_policy(self, root_name: str) -> str:
        n = root_name.lower()
        if "procurement act 2023 guidance documents collection" in n:
            return "PA_GUIDANCE_COLLECTION"
        if "procurement policy notes collection" in n:
            return "PPN_COLLECTION"
        if "trade agreements collection" in n:
            return "TRADE_COLLECTION"
        if "competition and markets authority" in n:
            return "CMA_ORGANISATION"
        return "CURATED_GOVUK"

    def _govuk_candidate_relevant(self, policy: str, text: str, depth: int,
                                  relationship: str) -> Tuple[bool, str]:
        t = normalise_text(text)
        if policy == "PA_GUIDANCE_COLLECTION":
            ok = (
                "procurement act 2023" in t or
                "procurement-act-2023" in t or
                procurement_relevant(t)
            )
            return ok, "Procurement Act collection relevance gate"

        if policy == "PPN_COLLECTION":
            # Collection membership is not enough. It must actually be a PPN or
            # directly supporting procurement-policy content.
            ok = (
                "procurement policy note" in t or
                "procurement-policy-note" in t or
                re.search(r"\bppn\s*[-/]?\s*\d", t) is not None or
                procurement_relevant(t)
            )
            return ok, "PPN/direct procurement-policy relevance gate"

        if policy == "TRADE_COLLECTION":
            ok = trade_procurement_relevant(t)
            return ok, "trade agreement retained only when public-procurement obligations are present"

        if policy == "CMA_ORGANISATION":
            ok = has_any(t, CMA_TERMS)
            return ok, "CMA material retained only for procurement/cartel/bid-rigging relevance"

        # Explicitly curated GOV.UK publication/guidance roots are trusted at the
        # root. Child items must either be direct documents/attachments or remain
        # procurement relevant.
        if depth == 0:
            return True, "explicit curated GOV.UK seed"
        ok = relationship in {"HAS_ATTACHMENT", "HAS_DOCUMENT"} or procurement_relevant(t)
        return ok, "direct attachment/document or procurement-relevant child"

    def _crawl_govuk(self, root_url: str, root_name: str, group_id: str):
        # Queue: url, depth, parent, relationship, parent_relevant
        q = deque([(root_url, 0, None, "SEED", True)])
        seen: Set[str] = set()
        root_key = canonicalize(root_url)
        pages = 0
        policy = self._govuk_root_policy(root_name)

        while q:
            url, depth, parent, relationship, parent_relevant = q.popleft()
            cu = canonicalize(url)
            if cu in seen or depth > self.max_depth:
                continue
            seen.add(cu)
            pages += 1
            if pages > self.max_pages_per_root:
                self.truncated_roots.add(root_key)
                break

            initial_class = "DISCOVERY_ONLY" if depth == 0 and group_id in {"GOVUK_COLLECTION", "GOVUK_ORGANISATION", "GOVUK_PUBLICATION"} else "OFFICIAL_SUPPORT"
            rec = Record(
                url=cu, canonical_url=cu, root_url=root_key, root_name=root_name,
                group_id=group_id, depth=depth, parent_url=parent,
                relationship=relationship, corpus_class=initial_class,
                kind=kind_for_class(initial_class)
            )
            rec = self._put_record(rec)

            data = None
            try:
                api = govuk_api_url(cu)
                resp = self.fetch(api or cu)
                rec.status_code = resp.status_code
                rec.fetched_at = utc_now()
                rec.final_url = canonicalize(resp.url)
                rec.content_type = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
                rec.sha256 = hashlib.sha256(resp.content).hexdigest()
                if resp.status_code >= 400:
                    raise requests.HTTPError(f"HTTP {resp.status_code}")
                data = resp.json()
            except Exception as api_error:
                # Conservative HTML fallback: only direct attachments/documents
                # and procurement-relevant GOV.UK links are considered.
                try:
                    resp = self.fetch(cu)
                    self._save_response(rec, resp)
                    if resp.status_code >= 400:
                        raise requests.HTTPError(f"HTTP {resp.status_code}")
                    soup = BeautifulSoup(resp.content, "lxml")
                    main = soup.find("main") or soup.find("article") or soup.body or soup
                    body_text = main.get_text(" ", strip=True) if main else ""
                    candidate_text = f"{rec.title or ''} {cu} {body_text[:20000]}"
                    relevant, why = self._govuk_candidate_relevant(policy, candidate_text, depth, relationship)
                    if depth == 0 and group_id in {"GOVUK_COLLECTION", "GOVUK_ORGANISATION", "GOVUK_PUBLICATION"}:
                        rec.corpus_class = "DISCOVERY_ONLY"
                        rec.kind = "container"
                        rec.relevant = False
                        rec.reason = "curated GOV.UK discovery/landing page"
                    elif relevant:
                        rec.corpus_class = "OFFICIAL_SUPPORT"
                        rec.kind = "evidence"
                        rec.relevant = True
                        rec.reason = why
                    else:
                        rec.corpus_class = "EXCLUDE"
                        rec.kind = "excluded"
                        rec.relevant = False
                        rec.reason = why

                    links = []
                    if relevant or depth == 0:
                        for a in soup.find_all("a", href=True):
                            raw = a.get("href")
                            if not raw or raw.startswith(("mailto:", "tel:", "javascript:")):
                                continue
                            child = canonicalize(urljoin(cu, raw))
                            if looks_like_non_document(child):
                                continue
                            label = a.get_text(" ", strip=True)
                            host = hostname(child)
                            if host == "assets.publishing.service.gov.uk" or suffix(child):
                                links.append((child, "HAS_ATTACHMENT", label))
                            elif host in {"www.gov.uk", "gov.uk"} and depth == 0:
                                ok, _ = self._govuk_candidate_relevant(policy, label + " " + child, depth + 1, "DIRECT_MEMBER")
                                if ok or policy == "TRADE_COLLECTION":
                                    links.append((child, "DIRECT_MEMBER", label))
                    rec.children_found = len(links)
                    for child, rel, label in links:
                        if rel == "HAS_ATTACHMENT":
                            if relevant or depth == 0:
                                self._fetch_leaf(
                                    child, root_key, root_name, group_id, depth + 1, cu,
                                    rel, "OFFICIAL_SUPPORT", "direct attachment of relevant GOV.UK content"
                                )
                        elif depth < self.max_depth:
                            q.append((child, depth + 1, cu, rel, relevant))
                    continue
                except Exception as html_error:
                    rec.kind = "error"
                    rec.reason = f"Content API failed: {api_error!r}; HTML fallback failed: {html_error!r}"
                    self.errors.append({"url": cu, "error": rec.reason})
                    continue

            rec.title = data.get("title")
            rec.content_id = data.get("content_id")
            rec.govuk_document_type = data.get("document_type")
            rec.govuk_content_purpose = data.get("content_purpose_supergroup")
            details = data.get("details") or {}
            details_text = details_to_text(details)
            candidate_text = " ".join([
                rec.title or "", cu, rec.govuk_document_type or "",
                rec.govuk_content_purpose or "", details_text[:40000]
            ])
            relevant, relevance_reason = self._govuk_candidate_relevant(policy, candidate_text, depth, relationship)

            doc_type = (rec.govuk_document_type or "").lower()
            if depth == 0 and group_id in {"GOVUK_COLLECTION", "GOVUK_ORGANISATION", "GOVUK_PUBLICATION"}:
                rec.corpus_class = "DISCOVERY_ONLY"
                rec.kind = "container"
                rec.relevant = False
                rec.reason = "curated GOV.UK collection/organisation/publication landing page"
            elif doc_type in GOVUK_CONTAINER_TYPES:
                rec.corpus_class = "DISCOVERY_ONLY"
                rec.kind = "container"
                rec.relevant = False
                rec.reason = "GOV.UK container/index content item"
            elif relevant:
                rec.corpus_class = "OFFICIAL_SUPPORT"
                rec.kind = "evidence"
                rec.relevant = True
                rec.reason = relevance_reason
            else:
                rec.corpus_class = "EXCLUDE"
                rec.kind = "excluded"
                rec.relevant = False
                rec.reason = relevance_reason

            # 1) Attachments/documents embedded in details are strong children.
            detail_children: Set[Tuple[str, str]] = set()
            for key in ("attachments", "documents"):
                vals = details.get(key) or []
                if isinstance(vals, dict):
                    vals = [vals]
                for item in vals:
                    if not isinstance(item, dict):
                        continue
                    for uk in ("url", "attachment_url", "web_url"):
                        u = item.get(uk)
                        if u:
                            rel = "HAS_ATTACHMENT" if key == "attachments" else "HAS_DOCUMENT"
                            detail_children.add((canonicalize(urljoin("https://www.gov.uk", u)), rel))

            # 2) Content API links: only direct child-like relations may propagate.
            link_children: Set[Tuple[str, str, str]] = set()
            links_obj = data.get("links") or {}
            for rel, vals in links_obj.items():
                if not isinstance(vals, list):
                    continue
                rel_l = rel.lower()
                if rel_l in GOVUK_NAV_RELATIONS:
                    # Important: generic related/navigation links never recurse.
                    continue
                for item in vals:
                    if not isinstance(item, dict):
                        continue
                    web_url = item.get("web_url")
                    base_path = item.get("base_path")
                    child = canonicalize(web_url) if web_url else (
                        canonicalize("https://www.gov.uk" + base_path) if base_path else None
                    )
                    if not child or child == cu:
                        continue
                    title = item.get("title") or ""
                    child_text = f"{title} {child} {item.get('document_type') or ''}"
                    if rel_l in GOVUK_CHILD_RELATIONS:
                        link_children.add((child, "DIRECT_MEMBER", child_text))
                    elif depth == 0 and group_id in {"GOVUK_COLLECTION", "GOVUK_ORGANISATION"}:
                        # Some collection schemas use a relation name not in our
                        # allow-list. At depth 0 only, permit candidate evaluation,
                        # but never trust it without the root-specific relevance gate.
                        link_children.add((child, "DIRECT_MEMBER", child_text))

            children_count = 0

            # Attachments are only retained if their parent is relevant, or if the
            # current node is an explicitly curated publication root.
            allow_attachments = relevant or (depth == 0 and group_id in {"GOVUK_PUBLICATION", "GOVUK_GUIDANCE"})
            if allow_attachments:
                for child, rel in sorted(detail_children):
                    if hostname(child) == "assets.publishing.service.gov.uk" or suffix(child):
                        self._fetch_leaf(
                            child, root_key, root_name, group_id, depth + 1, cu, rel,
                            "OFFICIAL_SUPPORT", "direct attachment/document of relevant GOV.UK content"
                        )
                        children_count += 1
                    elif hostname(child) in {"www.gov.uk", "gov.uk"} and depth < self.max_depth:
                        q.append((child, depth + 1, cu, rel, relevant))
                        children_count += 1

            # Collection members are evaluated one hop at a time. If a member is
            # irrelevant, it is recorded but its descendants are not traversed.
            if depth < self.max_depth and (depth == 0 or relevant):
                for child, rel, child_text in sorted(link_children):
                    if hostname(child) not in {"www.gov.uk", "gov.uk"}:
                        continue
                    pre_ok, _ = self._govuk_candidate_relevant(policy, child_text, depth + 1, rel)
                    if policy == "TRADE_COLLECTION" and depth == 0:
                        # Trade titles often omit procurement even when a procurement
                        # chapter exists, so inspect direct members once; body text will
                        # decide whether the member and its attachments survive.
                        pre_ok = True
                    if pre_ok:
                        q.append((child, depth + 1, cu, rel, relevant))
                        children_count += 1

            rec.children_found = children_count

    # ---------- legislation dependency policy ----------

    def _crawl_changes(self, root_url: str, root_name: str, group_id: str):
        rec = Record(
            url=root_url, canonical_url=root_url, root_url=root_url,
            root_name=root_name, group_id=group_id, depth=0, parent_url=None,
            relationship="SEED", kind="container", corpus_class="DISCOVERY_ONLY",
            relevant=False, reason="legislative changes metadata/discovery source"
        )
        self.records[root_url] = rec
        try:
            resp = self.fetch(root_url)
            self._save_response(rec, resp)
            if resp.status_code >= 400:
                raise requests.HTTPError(f"HTTP {resp.status_code}")
            soup = BeautifulSoup(resp.content, "lxml")
            children = set()
            pat = re.compile(r"^/(ukpga|uksi|ukla|asp|ssi|anaw|mwa|nia|nisr|ukcm)/\d{4}/\d+")
            for a in soup.find_all("a", href=True):
                child = canonicalize(urljoin(root_url, a["href"]))
                if hostname(child) == "www.legislation.gov.uk" and pat.match(urlparse(child).path):
                    parts = urlparse(child).path.strip("/").split("/")
                    if len(parts) >= 3:
                        instrument = "https://www.legislation.gov.uk/" + "/".join(parts[:3])
                        children.add(canonicalize(instrument))
            rec.children_found = len(children)
            for child in sorted(children):
                self._fetch_leaf(
                    child, root_url, root_name, group_id, 1, root_url,
                    "AFFECTS_TARGET_LEGISLATION", "LEGAL_DEPENDENCY",
                    "instrument discovered from Changes to Legislation effect data"
                )
        except Exception as e:
            rec.kind = "error"
            rec.reason = repr(e)
            self.errors.append({"url": root_url, "error": repr(e)})

    # ---------- generic/external relevance policy ----------

    def _external_policy(self, root_name: str) -> str:
        if root_name == "Build UK - Common Assessment Standard":
            return "BUILD_UK_CAS"
        if root_name == "Procurement Journey":
            return "PROCUREMENT_SITE"
        if root_name == "Mills & Reeve Procurement Portal":
            return "PROCUREMENT_SITE"
        if root_name == "Procurement Lawyers Association":
            return "PROCUREMENT_SITE"
        return "PRACTITIONER_SITE"

    def _external_relevant(self, policy: str, text: str) -> bool:
        if policy == "BUILD_UK_CAS":
            return has_any(text, CAS_TERMS)
        if policy == "PROCUREMENT_SITE":
            # Dedicated procurement sites are trusted topically, while still
            # excluding navigation/non-document pages.
            return True
        return procurement_relevant(text)

    def _crawl_generic(self, root_url: str, root_name: str, group_id: str,
                       force_procurement_site: bool = False):
        q = deque([(root_url, 0, None, "SEED")])
        seen: Set[str] = set()
        root_host = hostname(root_url)
        pages = 0
        policy = "PROCUREMENT_SITE" if force_procurement_site else self._external_policy(root_name)

        while q:
            url, depth, parent, relationship = q.popleft()
            cu = canonicalize(url)
            if cu in seen or depth > self.max_depth:
                continue
            seen.add(cu)
            pages += 1
            if pages > self.max_pages_per_root:
                self.truncated_roots.add(root_url)
                break

            seed_class = seed_corpus_class(group_id, root_name, root_url)
            rec_class = seed_class if depth == 0 else "SECONDARY"
            rec = Record(
                url=cu, canonical_url=cu, root_url=root_url, root_name=root_name,
                group_id=group_id, depth=depth, parent_url=parent,
                relationship=relationship, corpus_class=rec_class,
                kind=kind_for_class(rec_class)
            )
            rec = self._put_record(rec)

            try:
                resp = self.fetch(cu)
                self._save_response(rec, resp)
                if resp.status_code >= 400:
                    raise requests.HTTPError(f"HTTP {resp.status_code}")
                ct = rec.content_type or ""

                if "pdf" in ct or suffix(cu) in DOC_EXTENSIONS:
                    text = f"{rec.title or ''} {cu}"
                    relevant = self._external_relevant(policy, text)
                    if depth == 0 or relevant:
                        rec.corpus_class = "OFFICIAL_SUPPORT" if group_id == "PROCUREMENT_PATHWAY" else "SECONDARY"
                        rec.kind = "evidence"
                        rec.relevant = True
                        rec.reason = "relevant direct document on selected procurement source"
                    else:
                        rec.corpus_class = "EXCLUDE"
                        rec.kind = "excluded"
                        rec.relevant = False
                        rec.reason = "document does not satisfy source-specific procurement relevance gate"
                    continue

                if "html" not in ct:
                    rec.corpus_class = "EXCLUDE"
                    rec.kind = "excluded"
                    rec.relevant = False
                    rec.reason = f"unsupported content type {ct}"
                    continue

                soup = BeautifulSoup(resp.content, "lxml")
                main = soup.find("main") or soup.find("article") or soup.body or soup
                body_text = main.get_text(" ", strip=True) if main else ""
                title = rec.title or ""
                relevant = self._external_relevant(policy, title + " " + cu + " " + body_text[:20000])

                if depth == 0 and seed_class == "DISCOVERY_ONLY":
                    rec.corpus_class = "DISCOVERY_ONLY"
                    rec.kind = "container"
                    rec.relevant = False
                    rec.reason = "curated discovery root"
                elif relevant and len(body_text) >= 400 and not looks_like_non_document(cu):
                    rec.corpus_class = "OFFICIAL_SUPPORT" if group_id == "PROCUREMENT_PATHWAY" else "SECONDARY"
                    rec.kind = "evidence"
                    rec.relevant = True
                    rec.reason = "page passed source-specific procurement relevance gate"
                elif depth == 0 and seed_class in EVIDENCE_CLASSES:
                    rec.corpus_class = seed_class
                    rec.kind = "evidence"
                    rec.relevant = True
                    rec.reason = "explicit curated seed"
                else:
                    rec.corpus_class = "EXCLUDE"
                    rec.kind = "excluded"
                    rec.relevant = False
                    rec.reason = "page failed source-specific procurement relevance gate"

                # Traverse narrowly. A relevant parent is not enough: the child
                # link itself must also be procurement/CAS relevant, except on a
                # dedicated procurement site.
                links = []
                if depth < self.max_depth and (depth == 0 or relevant or policy == "PROCUREMENT_SITE"):
                    for a in soup.find_all("a", href=True):
                        raw = a.get("href")
                        if not raw or raw.startswith(("mailto:", "tel:", "javascript:")):
                            continue
                        child = canonicalize(urljoin(cu, raw))
                        if hostname(child) != root_host or looks_like_non_document(child):
                            continue
                        label = a.get_text(" ", strip=True)
                        child_relevant = self._external_relevant(policy, label + " " + child)
                        if not child_relevant and policy != "PROCUREMENT_SITE":
                            continue
                        rel = "HAS_ATTACHMENT" if suffix(child) else "SAME_SITE_RELEVANT_LINK"
                        links.append((child, rel))

                unique_links = sorted(set(links))
                rec.children_found = len(unique_links)
                for child, rel in unique_links:
                    if suffix(child):
                        cls = "OFFICIAL_SUPPORT" if group_id == "PROCUREMENT_PATHWAY" else "SECONDARY"
                        self._fetch_leaf(
                            child, root_url, root_name, group_id, depth + 1, cu,
                            rel, cls, "direct relevant document from selected procurement source"
                        )
                    else:
                        q.append((child, depth + 1, cu, rel))
            except Exception as e:
                rec.kind = "error"
                rec.reason = repr(e)
                rec.fetched_at = utc_now()
                self.errors.append({"url": cu, "error": repr(e)})


def load_seeds(path: Path) -> List[Tuple[str, dict]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    roots = []
    for g in data.get("groups", []):
        gid = g.get("group_id", "UNKNOWN")
        for s in g.get("sources", []):
            roots.append((gid, s))
    return roots


def dedupe_evidence(records: Iterable[Record]) -> List[Record]:
    """Deduplicate logical evidence. GOV.UK content_id is strongest identity."""
    out = {}
    priority = {"CORE": 4, "LEGAL_DEPENDENCY": 3, "OFFICIAL_SUPPORT": 2, "SECONDARY": 1}
    for r in records:
        if r.kind != "evidence" or r.corpus_class not in EVIDENCE_CLASSES:
            continue
        if r.status_code is not None and r.status_code >= 400:
            continue
        key = ("content_id", r.content_id) if r.content_id else ("url", r.final_url or r.canonical_url)
        existing = out.get(key)
        if existing is None:
            out[key] = r
            continue
        if priority.get(r.corpus_class, 0) > priority.get(existing.corpus_class, 0):
            out[key] = r
        elif r.depth < existing.depth:
            out[key] = r
    return list(out.values())


def write_outputs(outdir: Path, crawler: Crawler, roots_count: int):
    outdir.mkdir(parents=True, exist_ok=True)
    records = list(crawler.records.values())
    evidence = dedupe_evidence(records)
    containers = [r for r in records if r.kind == "container"]
    services = [r for r in records if r.kind == "operational_service"]
    excluded = [r for r in records if r.kind == "excluded"]
    errors = [r for r in records if r.kind == "error"]

    by_group = Counter(r.group_id for r in evidence)
    by_class = Counter(r.corpus_class for r in evidence)
    by_host = Counter(hostname(r.final_url or r.canonical_url) for r in evidence)
    by_relationship = Counter(r.relationship for r in evidence)
    exclusion_reasons = Counter(r.reason or "unspecified" for r in excluded)

    exact = len(errors) == 0 and len(crawler.truncated_roots) == 0
    summary = {
        "crawl_completed_at": utc_now(),
        "seed_roots": roots_count,
        "unique_relevant_evidence_documents": len(evidence),
        "discovery_index_pages": len(containers),
        "excluded_irrelevant_records": len(excluded),
        "operational_services_excluded_from_document_count": len(services),
        "errors": len(errors),
        "truncated_roots": sorted(crawler.truncated_roots),
        "exact_count_certified": exact,
        "exactness_rule": "true only when no fetch errors and no root traversal truncation occurred",
        "count_by_corpus_class": dict(sorted(by_class.items())),
        "count_by_group": dict(sorted(by_group.items())),
        "count_by_host": dict(sorted(by_host.items())),
        "count_by_relationship": dict(sorted(by_relationship.items())),
        "exclusion_reasons": dict(sorted(exclusion_reasons.items()))
    }

    (outdir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (outdir / "documents.json").write_text(
        json.dumps([asdict(r) for r in sorted(evidence, key=lambda x: x.canonical_url)], indent=2),
        encoding="utf-8"
    )
    (outdir / "all_records.json").write_text(
        json.dumps([asdict(r) for r in sorted(records, key=lambda x: x.canonical_url)], indent=2),
        encoding="utf-8"
    )
    (outdir / "excluded.json").write_text(
        json.dumps([asdict(r) for r in sorted(excluded, key=lambda x: x.canonical_url)], indent=2),
        encoding="utf-8"
    )
    (outdir / "errors.json").write_text(json.dumps(crawler.errors, indent=2), encoding="utf-8")

    with (outdir / "documents.csv").open("w", newline="", encoding="utf-8") as f:
        fields = [
            "corpus_class", "relationship", "group_id", "root_name", "title",
            "canonical_url", "final_url", "content_type", "status_code", "depth",
            "parent_url", "reason", "content_id", "sha256", "fetched_at"
        ]
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in sorted(evidence, key=lambda x: (x.corpus_class, x.group_id, x.canonical_url)):
            d = asdict(r)
            w.writerow({k: d.get(k) for k in fields})

    return summary


def main():
    ap = argparse.ArgumentParser(
        description="Traverse procurement source roots using relationship-aware relevance filtering and count unique substantive documents."
    )
    ap.add_argument("--seeds", default="seeds.json", help="Path to source inventory/seeds JSON")
    ap.add_argument("--out", default="crawl_output_relevant", help="Output directory")
    ap.add_argument("--max-depth", type=int, default=4)
    ap.add_argument("--max-pages-per-root", type=int, default=5000)
    ap.add_argument("--timeout", type=int, default=25)
    ap.add_argument("--delay", type=float, default=0.15)
    ap.add_argument("--official-only", action="store_true", help="Skip generic external/practitioner domains")
    args = ap.parse_args()

    roots = load_seeds(Path(args.seeds))
    crawler = Crawler(
        timeout=args.timeout,
        delay=args.delay,
        max_depth=args.max_depth,
        max_pages_per_root=args.max_pages_per_root,
        include_external=not args.official_only
    )

    for i, (gid, root) in enumerate(roots, 1):
        print(f"[{i}/{len(roots)}] {gid}: {root['name']}", file=sys.stderr)
        crawler.crawl_root(root, gid)

    summary = write_outputs(Path(args.out), crawler, len(roots))
    print(json.dumps(summary, indent=2))
    if not summary["exact_count_certified"]:
        print("\nWARNING: count is NOT certified exact. Inspect errors.json and truncated_roots.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
