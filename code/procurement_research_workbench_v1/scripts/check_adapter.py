#!/usr/bin/env python3
"""Cheap production interface check. Does not query or modify an index."""
import inspect
import json
from prw.adapters import production_backend

def main():
    backend=production_backend()
    print(json.dumps({'backend':'ProductionAdapter','capabilities':sorted(backend.capabilities),
        'search_signature':str(inspect.signature(backend.retriever.search)),
        'two_lane_signature':str(inspect.signature(backend.retriever.search_two_lanes)),
        'status':'INTERFACE_CONSTRUCTED_NOT_A_RETRIEVAL_TEST',
        'next':'Run a public DEV scenario; inspect saved evidence text and trace before full execution.'},indent=2))
if __name__=='__main__':main()
