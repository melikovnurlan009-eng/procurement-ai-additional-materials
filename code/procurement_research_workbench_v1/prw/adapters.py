"""Production adapter built to the uploaded architecture contract.
This is integration code, not a claim that the unavailable local repository was run here.
"""
from __future__ import annotations
import importlib
import inspect
import json
import os
import sys
from dataclasses import asdict, is_dataclass
from pathlib import Path
from .contracts import Evidence, SearchRequest, SearchResponse, BINDING


def load_backend(factory: str):
    module,fn=factory.split(':',1)
    return getattr(importlib.import_module(module),fn)()


def _trace(obj):
    if is_dataclass(obj): return asdict(obj)
    if isinstance(obj,dict): return obj
    if hasattr(obj,'to_dict'): return obj.to_dict()
    return {'trace_not_serializable':type(obj).__name__}


def _require_kwargs(method,kwargs):
    sig=inspect.signature(method)
    unsupported=set(kwargs)-set(sig.parameters)
    if unsupported and not any(p.kind==p.VAR_KEYWORD for p in sig.parameters.values()):
        raise TypeError(f'{method.__name__} lacks required experiment parameters {sorted(unsupported)}; adapt explicitly, do not silently drop controls')
    return method(**kwargs)

class ProductionAdapter:
    def __init__(self,retriever):
        self.retriever=retriever
        self.capabilities={'search','global_graph','two_lanes'}
        if hasattr(retriever,'expand_from_anchor'):
            self.capabilities.add('targeted_graph')
    def _convert(self,rows):
        rows=list(rows)
        need=[r['chunk_id'] for r in rows if not r.get('text')]
        loaded=self.retriever.load(need) if need else {}
        if isinstance(loaded,list): loaded={r['chunk_id']:r for r in loaded}
        out=[]
        for r in rows:
            data={**loaded.get(r['chunk_id'],{}),**r}
            meta=data.get('metadata',{})
            if isinstance(meta,str): meta=json.loads(meta)
            data={**meta,**data}
            anchors=data.get('source_node_ids') or []
            if isinstance(anchors,str):
                try: anchors=json.loads(anchors)
                except json.JSONDecodeError: anchors=[anchors]
            if not isinstance(anchors,list) or any(not isinstance(a,str) for a in anchors):
                raise ValueError('source_node_ids must contain canonical string identifiers')
            anchors=list(anchors)
            if data.get('parent_node_id'): anchors.append(data['parent_node_id'])
            if data.get('node_id'): anchors.append(data['node_id'])
            if not data.get('text'): raise ValueError(f"Cannot recover exact text for {r['chunk_id']}")
            out.append(Evidence(chunk_id=data['chunk_id'],text=data['text'],citation=data.get('citation',''),
                 source_url=data.get('source_url',''),authority_class=data.get('authority_class','UNKNOWN'),
                 legal_regime=data.get('legal_regime','UNKNOWN'),jurisdiction=data.get('jurisdiction','UNKNOWN'),
                 canonical_ids=sorted(set(anchors)),score=float(data.get('final_score',data.get('score',0.))),
                 provenance={'adapter':'ProductionAdapter','original_score':data.get('final_score',data.get('score'))}))
        return out
    def search(self,request:SearchRequest) -> SearchResponse:
        common={'query':request.query,'candidates':request.candidates,'use_graph':request.graph,'hops':request.hops,'per_hop':request.fanout}
        if request.mode=='legal':
            raw=_require_kwargs(self.retriever.search_two_lanes,{**common,'top_k_legislation':request.depth,'top_k_other':request.depth})
            if not isinstance(raw,(tuple,list)) or len(raw)!=3: raise ValueError('Expected (legislation, other, trace)')
            law,other,trace=raw
            # Interleave for acquisition rank only; final bundle has declared 5/5 role quotas.
            mixed=[]
            for i in range(max(len(law),len(other))):
                if i<len(law): mixed.append(law[i])
                if i<len(other): mixed.append(other[i])
            rows=mixed
        else:
            raw=_require_kwargs(self.retriever.search,{**common,'top_k':request.depth,
                 'use_lexical':request.mode!='dense','use_dense':request.mode!='lexical',
                 'use_rerank':request.priors,'use_legislation_lane':False,'expand_query':False})
            if not isinstance(raw,(tuple,list)) or len(raw)!=2: raise ValueError('Expected (results, trace)')
            rows,trace=raw
        out=self._convert(rows)
        if request.lane!='both': out=[x for x in out if x.lane==request.lane]
        return SearchResponse(out,{'request':asdict(request),'production_trace':_trace(trace),
                   'candidate_depth_per_channel':request.candidates,
                   'legal_lane_return_depth_each':request.depth if request.mode=='legal' else None})
    def expand_from(self,anchor,query,request):
        if 'targeted_graph' not in self.capabilities:
            raise NotImplementedError('Targeted graph expansion is not implemented in the supplied production contract. Global graph search remains available.')
        raw=self.retriever.expand_from_anchor(anchor_id=anchor,query=query,hops=1,per_hop=request.fanout)
        rows,trace=raw
        return SearchResponse(self._convert(rows),{'targeted_graph':True,'production_trace':_trace(trace)})


def production_backend():
    root=os.environ.get('PRW_REPO_ROOT')
    if not root: raise ValueError('Set PRW_REPO_ROOT to the actual repository directory')
    root=Path(root).resolve()
    if not (root/'chunk_retrieval.py').exists(): raise ValueError('chunk_retrieval.py not found at PRW_REPO_ROOT')
    sys.path.insert(0,str(root))
    klass=importlib.import_module('chunk_retrieval').ChunkRetriever
    signature=inspect.signature(klass)
    values={'db_path':os.getenv('PRW_DB',str(root/'state/chunk_index_merged.sqlite3')),
            'db':os.getenv('PRW_DB',str(root/'state/chunk_index_merged.sqlite3')),
            'collection':os.getenv('PRW_COLLECTION','chunks__bge_m3__merged'),
            'qdrant_url':os.getenv('QDRANT_URL','http://localhost:6333'),
            'model_name':os.getenv('LOCAL_EMBEDDING_MODEL','BAAI/bge-m3')}
    kwargs={k:v for k,v in values.items() if k in signature.parameters}
    required=[k for k,p in signature.parameters.items() if p.default is p.empty and p.kind not in (p.VAR_POSITIONAL,p.VAR_KEYWORD)]
    if any(k not in kwargs for k in required):
        raise TypeError(f'Unrecognized constructor {signature}; provide a custom module:factory rather than guessing')
    return ProductionAdapter(klass(**kwargs))


class ReplayBackend:
    """Exact-request replay for smoke tests and debugging, never an adaptive evaluation substitute."""
    capabilities={'search','global_graph','two_lanes','targeted_graph'}
    def __init__(self,responses:list[list[Evidence]]):
        self.responses=responses; self.calls=[]
    def search(self,request):
        self.calls.append(request)
        index=len(self.calls)-1
        if index>=len(self.responses): raise ValueError('Fixture replay exhausted')
        return SearchResponse(self.responses[index],{'fixture':True,'operation':index+1})
    def expand_from(self,anchor,query,request): return self.search(request)
