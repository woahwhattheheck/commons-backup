"""Agent-facing envelopes and queries, independent of the legacy UI model."""
from .store import Store,SCHEMA_VERSION,now
from .agent_inventory import NOTE

class PeerStore(Store):
    def envelope(self,**items):
        return {"ok":True,"schema_version":SCHEMA_VERSION,"peer_api_version":"2.0.0","served_at":now(),
                "peer_note":NOTE,"counts_are_lower_bounds":True,**items}
    def peers(self,**filters):
        from .agent_queries import roster
        return roster(self,**filters)
