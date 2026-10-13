from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from controller import entrypoint
agent=entrypoint(carrot=True, cap=False)
