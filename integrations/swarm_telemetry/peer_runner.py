"""Add peer inventories and aggregates to the existing independent reader loop."""
from .runner import Runner

class PeerRunner(Runner):
    def collect_inventory(self):
        if not self.storage_ready("inventory"):return self.storage_wait("inventory")
        from .agent_inventory import collect_native_inventory
        collect_native_inventory(self.store,self.config)
        try:
            from .activity_queries import project
            project(self.store)
        except Exception as exc:self._source_error("peer_query_index",exc)
        try:
            from .github_metrics import collect
            collect(self.store,self.config)
            self.errors.pop("github_metrics",None)
        except Exception as exc:self._source_error("github_metrics",exc)
        return super().collect_inventory()
