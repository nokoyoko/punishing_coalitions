#!/usr/bin/env python3
import argparse, json
from analysis.stage_b_racefix import DEFAULT_SOURCE, generate_tables

if __name__=="__main__":
    p=argparse.ArgumentParser(description="Generate corrected Stage B tables without simulation")
    p.add_argument("--source",default=str(DEFAULT_SOURCE)); a=p.parse_args()
    print(json.dumps(generate_tables(a.source),indent=2))
