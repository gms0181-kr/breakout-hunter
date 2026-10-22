"""Separate output set; existing collector persistence is untouched."""
from . import persist
from pathlib import Path
persist.MODES['squeeze']=['public/squeeze-hunter.json','public/squeeze-cache.json','public/squeeze-state.json','public/squeeze-snapshots.json']+[str(p) for p in Path('public').glob('squeeze-series-*.json')]
if __name__=='__main__':persist.main('squeeze')
