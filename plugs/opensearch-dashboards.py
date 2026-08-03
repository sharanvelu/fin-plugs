"""Shared OpenSearch Dashboards asset plug.

One OpenSearch Dashboards container shared across every Fin project (fixed
name ``fin_opensearch_dashboards``), serving the web UI on port 5601. It
connects to the shared ``fin_opensearch`` cluster from the ``opensearch``
plug — enable that asset too, or Dashboards has nothing to talk to. Both run
with the security plugin disabled (the standard OpenSearch local-development
setup), so no credentials are involved.
"""

from __future__ import annotations

from fincli.plugs.base import ContainerSpec
from fincli.plugs.base import FinPlug
from fincli.plugs.base import PlugType
from fincli.plugs.base import PortMapping


class OpenSearchDashboardsPlug(FinPlug):
    name = "opensearch-dashboards"
    version = "1.0.0"
    plug_type = PlugType.ASSET
    description = (
        "Shared OpenSearch Dashboards web UI container (requires the opensearch asset)."
    )

    def asset_specs(self, env) -> list[ContainerSpec]:
        return [
            ContainerSpec(
                service="opensearch-dashboards",
                image="opensearchproject/opensearch-dashboards:3",
                container_name="fin_opensearch_dashboards",
                environment={
                    "OPENSEARCH_HOSTS": '["http://fin_opensearch:9200"]',
                    "DISABLE_SECURITY_DASHBOARDS_PLUGIN": "true",
                    # Enhanced Discover experience (with explore.enabled below).
                    "DATA_SOURCE_ENABLED": "true",
                    "WORKSPACE_ENABLED": "true",
                },
                # explore.enabled is not in the image entrypoint's env-var
                # whitelist; a leading-dash command is passed through to
                # opensearch-dashboards as a CLI setting override.
                command=["--explore.enabled=true"],
                ports=[PortMapping(container=5601, host=5601)],
                web_exposed=True,
                web_port=5601,
            )
        ]
