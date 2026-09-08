"""Example custom factory. Replace constructor args only if your actual signature differs.
Use --backend examples.backend_factory:create from the unpacked package root.
No credentials or proprietary data belong in this module.
"""
from prw.adapters import production_backend

def create():
    return production_backend()
