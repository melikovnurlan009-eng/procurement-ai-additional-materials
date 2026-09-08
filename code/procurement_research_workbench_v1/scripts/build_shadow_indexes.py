#!/usr/bin/env python3
import argparse
from pathlib import Path
from prw.io import read_jsonl,write_json,file_hash
from prw.shadow_fts import build_shadow

def main():
    p=argparse.ArgumentParser(description='Build three isolated FTS5 research indexes; never overwrite a live index.')
    p.add_argument('--chunks',required=True);p.add_argument('--enrichments',required=True);p.add_argument('--out',required=True)
    a=p.parse_args();out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    chunks=read_jsonl(a.chunks);extras=read_jsonl(a.enrichments)
    for arm in ('I0','I1','I2'):build_shadow(out/(arm+'.sqlite3'),chunks,extras,arm)
    write_json(out/'manifest.json',{'source_sha256':file_hash(a.chunks),'enrichment_sha256':file_hash(a.enrichments),'arms':['I0','I1','I2'],
        'research_indexes_only':True,'production_index_changed':False})
    print(out/'manifest.json')
if __name__=='__main__':main()
