"""Shared Postgres asset plug (fixed name ``fin_postgres``)."""
from __future__ import annotations

from fincli.config import Config
from fincli.plugs.base import ContainerSpec
from fincli.plugs.base import FinPlug
from fincli.plugs.base import PlugType
from fincli.plugs.base import PortMapping
from fincli.plugs.base import VolumeMount


class PostgresPlug(FinPlug):
    name = "postgres"
    version = "1.0.0"
    plug_type = PlugType.ASSET
    description = "Shared PostgreSQL database container."

    def asset_specs(self, env) -> list[ContainerSpec]:
        return [
            ContainerSpec(
                service="postgres",
                image="postgres:16-alpine",
                container_name="fin_postgres",
                environment={
                    "POSTGRES_USER": Config.ASSET_USERNAME,
                    "POSTGRES_PASSWORD": Config.ASSET_PASSWORD,
                    "POSTGRES_DB": Config.ASSET_DEFAULT_DATABASE,
                },
                ports=[
                    PortMapping(
                        container=5432,
                        host=5432)],
                volumes=[
                    VolumeMount(
                        host="fin_asset_postgres",
                        container="/var/lib/postgresql/data")],
            )]
