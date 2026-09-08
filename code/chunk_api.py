#!/usr/bin/env python3
"""Interactive service over the chunk-level retrieval system.

Serves the merged corpus (8,511 chunks, 27,824 edges) rather than the frozen baseline,
and exposes the retrieval configuration as request parameters so the arms compared in the
evaluation can be tried by hand:

    GET  /            browser page for manual testing
    GET  /health      corpus and index status
    POST /search      retrieval only, with the full trace
    POST /answer      cited answer over retrieved evidence
    GET  /chunk/{id}  exact source text of one chunk

Answers cite evidence by [E1] markers and are checked in code: citation coverage, invalid
markers, unverifiable quotes and claim grounding are returned alongside the answer rather
than being asserted.

Usage
-----
    .venv-embed/bin/python chunk_api.py --port 8899
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent

PAGE = r"""<!doctype html><meta charset="utf-8"><title>Procurement retrieval</title>
<style>
 body{font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;margin:0;
      background:#fcfcfb;color:#111}
 .wrap{max-width:1000px;margin:0 auto;padding:28px 20px 60px}
 h1{font-size:19px;margin:0 0 4px} .sub{color:#666;font-size:13px;margin-bottom:20px}
 textarea{width:100%;padding:11px;font:15px inherit;border:1px solid #d6d5d0;border-radius:7px;
      box-sizing:border-box;resize:vertical}
 .row{display:flex;gap:14px;align-items:center;flex-wrap:wrap;margin:12px 0}
 label{font-size:13px;color:#444;display:flex;gap:5px;align-items:center}
 button{background:#2a78d6;color:#fff;border:0;border-radius:7px;padding:9px 18px;
      font-size:14px;cursor:pointer} button:disabled{opacity:.5}
 button.alt{background:#52514e}
 .card{background:#fff;border:1px solid #e4e3df;border-radius:9px;padding:14px 16px;margin:11px 0}
 .meta{font-size:12px;color:#666;margin-bottom:5px}
 .cite{font-weight:600;font-size:14px}
 .txt{white-space:pre-wrap;font-size:13.5px;color:#333;margin-top:7px;
      max-height:230px;overflow:auto;border-left:3px solid #eee;padding-left:11px}
 .tag{display:inline-block;background:#eef4fc;color:#1a4f8a;border-radius:4px;
      padding:1px 7px;font-size:11px;margin-right:5px}
 .tag.g{background:#e6f6f0;color:#0d6b4b}
 .answer{background:#fff;border:1px solid #d6d5d0;border-left:4px solid #2a78d6;
      border-radius:9px;padding:16px 18px;white-space:pre-wrap;margin:14px 0}
 .checks{font-size:12.5px;color:#555;background:#f5f5f3;border-radius:7px;padding:10px 13px}
 .warn{color:#a04000}
 .copybar{display:flex;gap:8px;align-items:center;margin:10px 0 2px}
 .copy{background:#fff;border:1px solid #d6d5d0;border-radius:6px;padding:5px 11px;
      font-size:12.5px;color:#333;cursor:pointer}
 .copy:hover{background:#f2f2f0}
 .copy.ok{border-color:#1baf7a;color:#0d6b4b}
 .card .copy{padding:3px 9px;font-size:11.5px}
 .cardhead{display:flex;justify-content:space-between;align-items:flex-start;gap:10px}
 pre.plain{white-space:pre-wrap;font:13px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;
      background:#f7f7f5;border:1px solid #e4e3df;border-radius:8px;padding:13px;
      max-height:420px;overflow:auto;margin:8px 0 0}
</style>
<div class=wrap>
<h1>UK procurement retrieval <span style="font-size:11px;color:#999;font-weight:400">build 2</span></h1>
<div class=sub id=status>loading…</div>
<textarea id=q rows=3 placeholder="e.g. When can a supplier be excluded for bid rigging?"></textarea>
<div class=row>
  <label><input type=checkbox id=lex checked> BM25</label>
  <label><input type=checkbox id=dns checked> dense</label>
  <label><input type=checkbox id=grf checked> graph</label>
  <label><input type=checkbox id=rrk checked> authority rerank</label>
  <label><input type=checkbox id=qex> query expansion</label>
  <label>top-k <input type=number id=k value=8 min=1 max=30 style="width:52px"></label>
  <button id=go>Search</button>
  <button id=ans class=alt>Search + answer</button>
</div>
<div id=out></div>
</div>
<script>
const $=id=>document.getElementById(id);
fetch('/health').then(r=>r.json()).then(h=>{
  $('status').textContent = h.chunks.toLocaleString()+' chunks · '+h.edges.toLocaleString()
    +' edges · '+h.documents.toLocaleString()+' documents · dense '+(h.dense_ok?'ok':'unavailable');
}).catch(e=>{ $('status').textContent='status unavailable: '+e.message
    +' — search may still work'; });
function body(){return{query:$('q').value,top_k:+$('k').value,use_lexical:$('lex').checked,
  use_dense:$('dns').checked,use_graph:$('grf').checked,use_rerank:$('rrk').checked,
  expand_query:$('qex').checked};}
function esc(s){return (s||'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}
let LAST=null;
async function copyText(t,btn){
  try{ await navigator.clipboard.writeText(t); }
  catch(e){ const a=document.createElement('textarea'); a.value=t; document.body.appendChild(a);
            a.select(); document.execCommand('copy'); a.remove(); }
  if(btn){const o=btn.textContent; btn.textContent='Copied'; btn.classList.add('ok');
          setTimeout(()=>{btn.textContent=o; btn.classList.remove('ok');},1400);}
}
// Full record as plain text: question, answer, verification, and every evidence item
// with its citation, authority, source URL and exact wording.
function asText(d){
  const L=[];
  L.push('QUESTION: '+d.query);
  if(d.regime) L.push('REGIME:   '+d.regime);
  L.push('');
  if(d.answer){
    L.push('ANSWER'); L.push('------'); L.push(d.answer); L.push('');
    if(d.unanswered_aspects && d.unanswered_aspects.length){
      L.push('NOT ANSWERED BY THE EVIDENCE');
      d.unanswered_aspects.forEach(u=>L.push('  - '+u)); L.push('');
    }
    const c=d.citation_checks;
    L.push('VERIFICATION');
    L.push('  citation coverage : '+(c.citation_coverage??'n/a'));
    L.push('  evidence cited    : '+c.evidence_cited+'/'+c.evidence_supplied);
    L.push('  invalid citations : '+c.invalid_citations.length);
    if(c.claim_grounding) L.push('  claim grounding   : '+c.claim_grounding.grounded_claims+'/'+c.claim_grounding.claims);
    L.push('  grounded          : '+(c.substantive_pass?'yes':'NO'));
    L.push('  citation format   : '+(c.format_pass?'ok':'markers missing'));
    L.push('  result            : '+(c.passed?'passed':'FAILED'));
    L.push('');
  }
  L.push('RETRIEVAL');
  L.push('  lexical '+d.trace.lexical+' | dense '+d.trace.dense+' | anchors '+d.trace.anchors
        +' | edges '+d.trace.edges+' | graph-added '+d.trace.graph_added);
  if(d.trace.expansion) L.push('  query expansion: '+d.trace.expansion.join(', '));
  L.push('');
  L.push('EVIDENCE'); L.push('--------');
  d.results.forEach((r,i)=>{
    L.push('['+(d.answer?'E':'')+(i+1)+'] '+(r.citation||r.document_id));
    L.push('     authority: '+(r.authority_class||'?')+(r.legal_regime?' | regime: '+r.legal_regime:'')
          +(r.via_graph_only?' | reached via graph':'')+' | score '+r.final_score.toFixed(4));
    if(r.retrieval_title) L.push('     title: '+r.retrieval_title);
    if(r.source_url) L.push('     source: '+r.source_url);
    L.push('');
    L.push((r.text||'').split('\n').map(x=>'     '+x).join('\n'));
    L.push('');
  });
  return L.join('\n');
}
function chunkText(r,i){
  return (r.citation||r.document_id)+'\n'
    +(r.source_url? r.source_url+'\n':'')+'\n'+(r.text||'');
}
function results(d){
  let h='<div class=sub>lexical '+d.trace.lexical+' · dense '+d.trace.dense+' · anchors '
    +d.trace.anchors+' · edges '+d.trace.edges+' · graph-added '+d.trace.graph_added;
  if(d.trace.expansion) h+=' · expanded: '+esc(d.trace.expansion.join(', '));
  h+='</div>';
  d.results.forEach((r,i)=>{
    h+='<div class=card><div class=cardhead><div><div class=meta><span class=tag>'
      +esc(r.authority_class||'?')+'</span>'
      +(r.legal_regime?'<span class=tag>'+esc(r.legal_regime)+'</span>':'')
      +(r.via_graph_only?'<span class="tag g">via graph</span>':'')
      +' score '+r.final_score.toFixed(4)+'</div>'
      +'<div class=cite>'+esc(r.citation||r.document_id)+'</div></div>'
      +'<button class=copy data-chunk="'+i+'">Copy</button></div>'
      +'<div class=meta>'+esc(r.retrieval_title||'')+'</div>'
      +'<div class=txt>'+esc(r.text)+'</div>'
      +(r.source_url?'<div class=meta><a href="'+esc(r.source_url)+'" target=_blank>source</a></div>':'')
      +'</div>';
  });
  return h;
}
async function run(url){
  const o=$('out'); o.innerHTML='<div class=sub>working…</div>';
  $('go').disabled=$('ans').disabled=true;
  try{
    const r=await fetch(url,{method:'POST',headers:{'content-type':'application/json'},
      body:JSON.stringify(body())});
    const d=await r.json();
    if(!r.ok){o.innerHTML='<div class="card warn">'+esc(d.detail||'error')+'</div>';return;}
    let h='';
    if(d.answer){
      h+='<div class=answer>'+esc(d.answer)+'</div>';
      const c=d.citation_checks;
      h+='<div class=checks><b>verification</b> — regime: '+esc(d.regime||'n/a')
        +' · citation coverage '+(c.citation_coverage??'n/a')
        +' · evidence cited '+c.evidence_cited+'/'+c.evidence_supplied
        +' · invalid citations '+c.invalid_citations.length
        +' · claim grounding '+(c.claim_grounding? c.claim_grounding.grounded_claims+'/'+c.claim_grounding.claims : 'n/a')
        +' · <b>'+(c.passed?'passed':'FAILED')+'</b></div>';
    }
    LAST=d;
    const bar='<div class=copybar>'
      +'<button class=copy id=cpAll>Copy everything</button>'
      +(d.answer?'<button class=copy id=cpAns>Copy answer only</button>':'')
      +'<button class=copy id=cpCit>Copy citations</button>'
      +'<button class=copy id=cpTxt>Show plain text</button></div>';
    o.innerHTML=bar+h+results(d)+'<pre class=plain id=plain style="display:none"></pre>';
    $('cpAll').onclick=e=>copyText(asText(d),e.target);
    if($('cpAns')) $('cpAns').onclick=e=>copyText(d.answer,e.target);
    $('cpCit').onclick=e=>copyText(d.results.map((r,i)=>
        '['+(d.answer?'E':'')+(i+1)+'] '+(r.citation||r.document_id)
        +(r.source_url? ' — '+r.source_url:'')).join('\n'),e.target);
    $('cpTxt').onclick=e=>{const pl=$('plain');
        if(pl.style.display==='none'){pl.textContent=asText(d);pl.style.display='block';
          e.target.textContent='Hide plain text';}
        else{pl.style.display='none';e.target.textContent='Show plain text';}};
    o.querySelectorAll('.copy[data-chunk]').forEach(b=>{
        b.onclick=ev=>copyText(chunkText(d.results[+b.dataset.chunk],+b.dataset.chunk),ev.target);});
  }catch(e){o.innerHTML='<div class="card warn">'+esc(e.message)+'</div>';}
  finally{$('go').disabled=$('ans').disabled=false;}
}
$('go').onclick=()=>run('/search'); $('ans').onclick=()=>run('/answer');
$('q').addEventListener('keydown',e=>{if(e.key==='Enter'&&(e.metaKey||e.ctrlKey))run('/search');});
</script>"""


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    top_k: int = Field(default=8, ge=1, le=30)
    candidates: int = Field(default=40, ge=10, le=200)
    use_lexical: bool = True
    use_dense: bool = True
    use_graph: bool = True
    use_rerank: bool = True
    expand_query: bool = False


class RefineRequest(BaseModel):
    original_query: str = Field(min_length=1, max_length=4000)
    previous_answer: str = Field(min_length=1, max_length=8000)
    correction: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=8, ge=1, le=30)


def create_app(db: Path, collection: str, model: str) -> FastAPI:
    import sys
    sys.path.insert(0, str(ROOT))
    from chunk_retrieval import ChunkRetriever

    app = FastAPI(title="Procurement chunk retrieval", version="1.0.0")
    retriever = ChunkRetriever(db, collection)

    # Load the embedding model before serving. It takes about a minute, and doing it
    # lazily meant the first request - which is the page's own /health call - blocked for
    # that long, so the page appeared to hang on load.
    print("  loading embedding model (about a minute) ...", flush=True)
    try:
        retriever.dense("warmup", 1)
        print("  embedding model ready", flush=True)
        dense_state = {"ok": True, "error": None}
    except Exception as exc:
        print(f"  dense channel unavailable: {exc}", flush=True)
        dense_state = {"ok": False, "error": str(exc)[:300]}

    def run_search(req: SearchRequest):
        results, trace = retriever.search(
            req.query, top_k=req.top_k, candidates=req.candidates,
            use_lexical=req.use_lexical, use_dense=req.use_dense,
            use_graph=req.use_graph, use_rerank=req.use_rerank,
            expand_query=req.expand_query,
        )
        exp = (trace.config or {}).get("query_expansion") or {}
        return results, {
            "lexical": len(trace.lexical_hits), "dense": len(trace.dense_hits),
            "anchors": len(trace.anchors), "edges": len(trace.edges_traversed),
            "graph_added": len(trace.graph_added),
            "legacy_query": trace.legacy_query,
            "expansion": exp.get("statutory_terms"),
        }

    @app.get("/", response_class=HTMLResponse)
    def index() -> HTMLResponse:
        return HTMLResponse(PAGE, headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        })

    @app.get("/health")
    def health() -> dict[str, Any]:
        con = sqlite3.connect(db)
        out = {
            "corpus_db": str(db), "collection": collection, "answer_model": model,
            "chunks": con.execute("SELECT COUNT(*) FROM chunks").fetchone()[0],
            "edges": con.execute("SELECT COUNT(*) FROM edges").fetchone()[0],
            "documents": con.execute("SELECT COUNT(*) FROM documents").fetchone()[0],
            "openai_key_present": bool(os.environ.get("OPENAI_API_KEY")),
        }
        con.close()
        # Reports the state established at startup; never triggers a model load, so the
        # endpoint stays fast and the page can render immediately.
        out["dense_ok"] = dense_state["ok"]
        if dense_state["error"]:
            out["dense_error"] = dense_state["error"]
        return out

    @app.post("/search")
    def search(req: SearchRequest) -> dict[str, Any]:
        results, trace = run_search(req)
        return {"query": req.query, "trace": trace, "results": results}

    def generate_answer(query: str, top_k: int, use_graph: bool = True) -> dict[str, Any]:
        """Retrieve, generate a cited answer, and verify it. Shared by /answer and
        /refine so a refined query goes through exactly the same path as a fresh one -
        the correction loop must not get a different, unverified answer path."""
        from answer_query import build_evidence_two_lanes, verify, check_claim_grounding, \
            SYSTEM_PROMPT, ANSWER_SCHEMA
        from openai import OpenAI

        legislation, other, raw_trace = retriever.search_two_lanes(
            query, top_k_legislation=top_k, top_k_other=top_k, use_graph=use_graph,
        )
        items = build_evidence_two_lanes(legislation, other, 4000)
        results = legislation + other
        trace = {
            "lexical": len(raw_trace.lexical_hits), "dense": len(raw_trace.dense_hits),
            "anchors": len(raw_trace.anchors), "edges": len(raw_trace.edges_traversed),
            "graph_added": len(raw_trace.graph_added), "legacy_query": raw_trace.legacy_query,
            "legislation_lane_count": len(legislation), "other_lane_count": len(other),
        }
        if not items:
            raise HTTPException(404, "no evidence retrieved for this query")
        client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        payload = {"question": query, "evidence": [
            {k: v for k, v in it.items()
             if k in ("id", "citation", "authority_class", "legal_regime", "lane", "text")}
            for it in items]}
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": SYSTEM_PROMPT},
                      {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
            response_format={"type": "json_schema", "json_schema": {
                "name": "cited_answer", "schema": ANSWER_SCHEMA, "strict": True}},
            temperature=0,
        )
        out = json.loads(resp.choices[0].message.content)
        checks = verify(out["answer"], items)
        grounding = check_claim_grounding(out.get("claims") or [], items)
        checks["claim_grounding"] = grounding
        checks["substantive_pass"] = bool(checks["citations_valid"]) and (
            grounding.get("grounding_rate") or 0) >= 0.6
        checks["passed"] = bool(checks["substantive_pass"]) and bool(checks["format_pass"])
        return {"query": query, "answer": out["answer"], "regime": out.get("regime"),
                "claims": out.get("claims"), "unanswered_aspects": out.get("unanswered_aspects"),
                "citation_checks": checks, "trace": trace, "results": results,
                "legislation_lane": [{k: v for k, v in r.items() if k != "text"} for r in legislation],
                "other_lane": [{k: v for k, v in r.items() if k != "text"} for r in other]}

    @app.post("/answer")
    def answer(req: SearchRequest) -> dict[str, Any]:
        if not os.environ.get("OPENAI_API_KEY"):
            raise HTTPException(503, "OPENAI_API_KEY not set; /search works without it")
        return generate_answer(req.query, req.top_k, req.use_graph)

    @app.post("/refine")
    def refine_endpoint(req: RefineRequest) -> dict[str, Any]:
        """The chatbot-correction loop: interpret what the user's correction means, turn
        it into a new retrieval query, re-retrieve and re-answer through the same path as
        /answer. Measured on the 150-query test set (evaluation/refinement, see
        reproducibility/session_v3): a naive baseline of just appending the correction
        text to the original query recovers the right provision in 11.8% of cases where
        the first answer was wrong; interpreting the correction and reformulating the
        query recovers 31.4% - the diagnosis step is not cosmetic, it is most of the
        effect."""
        if not os.environ.get("OPENAI_API_KEY"):
            raise HTTPException(503, "OPENAI_API_KEY not set")
        from refine_query import refine

        diagnosis = refine(req.original_query, req.previous_answer, req.correction, model=model)
        new_query = diagnosis.get("new_query") or req.original_query
        result = generate_answer(new_query, req.top_k)
        result["refinement"] = {
            "original_query": req.original_query, "correction": req.correction,
            "diagnosis": diagnosis.get("diagnosis"), "reasoning": diagnosis.get("reasoning"),
            "new_query": new_query,
        }
        return result

    @app.get("/chunk/{chunk_id}")
    def chunk(chunk_id: str) -> dict[str, Any]:
        con = sqlite3.connect(db)
        con.row_factory = sqlite3.Row
        row = con.execute("SELECT * FROM chunks WHERE chunk_id = ?", (chunk_id,)).fetchone()
        con.close()
        if not row:
            raise HTTPException(404, "chunk not found")
        return dict(row)

    return app


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="state/chunk_index_merged.sqlite3", type=Path)
    ap.add_argument("--collection", default="chunks__bge_m3__merged")
    ap.add_argument("--model", default=os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini"))
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8899)
    args = ap.parse_args()

    import uvicorn

    db = args.db if args.db.is_absolute() else ROOT / args.db
    app = create_app(db, args.collection, args.model)
    print(f"\n  ready:  http://127.0.0.1:{args.port}\n", flush=True)
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
