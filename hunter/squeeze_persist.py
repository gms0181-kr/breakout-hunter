"""Separate output set; existing collector persistence is untouched."""
from . import persist
persist.MODES['squeeze']=['public/squeeze-hunter.json','public/squeeze-cache.json','public/squeeze-state.json','public/squeeze-snapshots.json']
if __name__=='__main__':persist.main('squeeze')
