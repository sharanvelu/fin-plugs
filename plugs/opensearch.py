"""Shared OpenSearch asset plug.

One single-node OpenSearch container shared across every Fin project (fixed
name ``fin_opensearch``). The security plugin is disabled — the standard
OpenSearch local-development setup — so the cluster is reachable at
``http://fin_opensearch:9200`` (host: ``http://localhost:9200``) with no
credentials. (OpenSearch >= 2.12 rejects weak admin passwords, so Fin's shared
``Config.ASSET_PASSWORD`` cannot seed a secured cluster.)

Pair with the ``opensearch-dashboards`` plug for the web UI.
"""

from __future__ import annotations

from fincli.plugs.base import ContainerSpec
from fincli.plugs.base import FinPlug
from fincli.plugs.base import PlugType
from fincli.plugs.base import PortMapping
from fincli.plugs.base import VolumeMount


class OpenSearchPlug(FinPlug):
    name = "opensearch"
    version = "1.0.0"
    plug_type = PlugType.ASSET
    description = "Shared OpenSearch search/analytics container (single node)."

    def asset_specs(self, env) -> list[ContainerSpec]:
        return [
            ContainerSpec(
                service="opensearch",
                image="opensearchproject/opensearch:3",
                container_name="fin_opensearch",
                environment={
                    "cluster.name": "fin_opensearch_cluster",
                    "node.name": "fin_opensearch",
                    "discovery.type": "single-node",
                    "bootstrap.memory_lock": "true",
                    # Cap the JVM heap for local dev (default takes half of RAM).
                    "OPENSEARCH_JAVA_OPTS": "-Xms512m -Xmx512m",
                    "DISABLE_INSTALL_DEMO_CONFIG": "true",
                    "DISABLE_SECURITY_PLUGIN": "true",
                },
                ports=[
                    # REST API.
                    PortMapping(container=9200, host=9200),
                    # Performance Analyzer.
                    PortMapping(container=9600, host=9600),
                ],
                volumes=[
                    VolumeMount(
                        host="fin_asset_opensearch",
                        container="/usr/share/opensearch/data",
                    )
                ],
                extra={
                    # bootstrap.memory_lock needs an unlimited memlock ulimit;
                    # nofile matches the upstream compose recommendation.
                    "ulimits": [
                        {"name": "memlock", "soft": -1, "hard": -1},
                        {"name": "nofile", "soft": 65536, "hard": 65536},
                    ],
                },
            )
        ]
