# SPDX-License-Identifier: Apache-2.0
"""Evaluation binding to the unmodified packaged TitanAgent, one instance per game."""
import json
from pathlib import Path
import sys
_INSTANCE=None


def call(obs,cfg,enabled):
    global _INSTANCE
    if _INSTANCE is None:
        root=Path(json.loads(Path(__file__).with_name('runtime-resolution.json').read_text())['archive_root'])
        sys.path.insert(0,str(root))
        from titan_runtime import TitanAgent,Features
        config=json.loads((root/'TITAN-HISTORY-CONFIG.json').read_text())
        config['terminal_history']=enabled
        _INSTANCE=TitanAgent(Features(**config))
    action=_INSTANCE.act(obs,cfg)
    metadata={'diagnostics':_INSTANCE.diagnostics}
    if int(obs['step'])==718 and _INSTANCE.history is not None:
        history=_INSTANCE.history.bridge.history
        metadata['history_records']={p:{str(t):r.as_dict() for t,r in rows.items()} for p,rows in history.records.items()}
        metadata['history_counts']={'identified':history.identified,'censored':history.censored}
    # Driver removes this evaluation envelope before the official interpreter.
    return {**action,'__consumer_evidence__':metadata}


def history_on(obs,cfg):return call(obs,cfg,True)
def history_off(obs,cfg):return call(obs,cfg,False)
