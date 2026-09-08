"""Optional exact one-hop citation sidecar; requires explicit live node-to-chunk mapping.
No inferred edges, nearest-ancestor guesses, CONTAINS or HAS_CHUNK semantic expansion.
"""
from __future__ import annotations
from .contracts import SearchResponse

class GraphSidecar:
    def __init__(self,backend,edges,live_node_map,load_evidence):
        self.backend=backend;self.load_evidence=load_evidence;self.live_node_map=live_node_map
        self.capabilities=set(backend.capabilities)|{'targeted_graph'}
        self.adjacency={}
        for e in edges:
            if e.get('relation') not in {'CROSS_REFERS_TO','REFERENCES'}: continue
            if not e.get('source_id') or not e.get('target_id'): raise ValueError('Incomplete graph edge')
            # Traversal may follow either direction, but the original relation is never reversed semantically.
            for start,end,direction in [(e['source_id'],e['target_id'],'outgoing'),(e['target_id'],e['source_id'],'incoming')]:
                self.adjacency.setdefault(start,[]).append((end,direction,e))
    def search(self,request):return self.backend.search(request)
    def expand_from(self,anchor,query,request):
        if request.hops!=1:raise ValueError('Sidecar is explicitly one-hop')
        edges=sorted(self.adjacency.get(anchor,[]),key=lambda x:(-float(x[2].get('confidence',0)),x[0],x[2]['relation']))[:request.fanout]
        ids=[];trace=[]
        for target,direction,e in edges:
            mapped=self.live_node_map.get(target,[])
            ids.extend(mapped)
            trace.append({'anchor':anchor,'traversal_direction':direction,'edge_source':e['source_id'],
                          'edge_target':e['target_id'],'relation':e['relation'],'reached_node':target,
                          'mapped_chunk_ids':mapped,'mapping_status':'EXACT_LIVE_MAPPING' if mapped else 'NO_LIVE_MAPPING'})
        unique=list(dict.fromkeys(ids))
        evidence=self.load_evidence(unique)
        if {e.chunk_id for e in evidence}-set(unique):raise ValueError('Loader returned unrequested chunk IDs')
        return SearchResponse(evidence,{'graph_query':query,'one_hop':True,'edges':trace,'source_count':len(unique),
                                       'ranking':'edge confidence then stable ID; semantic reranking not asserted'})
