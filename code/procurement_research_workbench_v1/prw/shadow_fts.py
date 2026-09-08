"""Isolated SQLite FTS5 indexes for an exact-keyword/alias ablation.
Never modifies the production corpus, graph, vector store, or source text.
"""
from __future__ import annotations
import json
import re
import sqlite3
from pathlib import Path
from .io import digest


def build_shadow(path,chunks,enrichments=None,arm='I0'):
    if arm not in {'I0','I1','I2'}: raise ValueError('arm must be I0/I1/I2')
    path=Path(path)
    if path.exists(): raise FileExistsError('Shadow index exists; choose a new versioned path')
    path.parent.mkdir(parents=True,exist_ok=True)
    extras={e['chunk_id']:e for e in enrichments or []}
    db=sqlite3.connect(path)
    try:
        db.execute('CREATE TABLE chunks (chunk_id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
        db.execute("CREATE VIRTUAL TABLE fts USING fts5(chunk_id UNINDEXED,text,title,citation,keywords,aliases,tokenize='porter')")
        for c in chunks:
            e=extras.get(c['chunk_id'])
            if e and e['source_text_sha256']!=digest(c['text']): raise ValueError('Enrichment is stale')
            keywords=c.get('keywords','')
            if isinstance(keywords,list): keywords=' '.join(keywords)
            if e and arm in {'I1','I2'}: keywords+=' '+' '.join(x['term'] for x in e['exact_keywords'])
            aliases=' '.join(x['term'] for x in e.get('aliases',[])) if e and arm=='I2' else ''
            db.execute('INSERT INTO chunks VALUES (?,?)',(c['chunk_id'],json.dumps(c)))
            db.execute('INSERT INTO fts VALUES (?,?,?,?,?,?)',(c['chunk_id'],c['text'],c.get('retrieval_title',''),c.get('citation',''),keywords,aliases))
        db.execute('CREATE TABLE manifest (arm TEXT, count INTEGER)')
        db.execute('INSERT INTO manifest VALUES (?,?)',(arm,len(chunks)))
        db.commit()
    except Exception:
        db.close(); path.unlink(missing_ok=True); raise
    db.close()


def search_shadow(path,query,k=20,weights=(0,1,1,1,1,1)):
    if len(weights)!=6: raise ValueError('Six FTS column weights required, including unindexed ID')
    terms=re.findall(r'[A-Za-z0-9]+',query)[:100]
    if not terms: return []
    expression=' OR '.join('"'+t+'"' for t in terms)
    db=sqlite3.connect('file:'+str(Path(path).resolve())+'?mode=ro',uri=True)
    try:
        # Only numeric validated weights interpolated; search text remains parameterized.
        ws=','.join(str(float(w)) for w in weights)
        sql=f'SELECT fts.chunk_id, bm25(fts,{ws}), chunks.payload FROM fts JOIN chunks ON chunks.chunk_id=fts.chunk_id WHERE fts MATCH ? ORDER BY bm25(fts,{ws}) LIMIT ?'
        return [{'chunk_id':cid,'score':-score,'payload':json.loads(payload)} for cid,score,payload in db.execute(sql,(expression,k))]
    finally: db.close()
