"""Shared Redis asset plug (fixed name ``fin_redis``)."""
from __future__ import annotations

from fincli.plugs.base import ContainerSpec
from fincli.plugs.base import FinPlug
from fincli.plugs.base import PlugType
from fincli.plugs.base import PortMapping
from fincli.plugs.base import VolumeMount


class RedisPlug(FinPlug):
    name = "redis"
    version = "1.0.0"
    plug_type = PlugType.ASSET
    description = "Shared Redis container."

    def asset_specs(self, env) -> list[ContainerSpec]:
        return [
            ContainerSpec(
                service="redis",
                image="redis:7-alpine",
                container_name="fin_redis",
                ports=[
                    PortMapping(
                        container=6379,
                        host=6379)],
                volumes=[
                    VolumeMount(
                        host="fin_asset_redis",
                        container="/data")],
            )]
