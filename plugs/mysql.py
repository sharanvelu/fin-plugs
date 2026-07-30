"""Shared MySQL asset plug.

One MySQL container shared across every Fin project (fixed name ``fin_mysql``),
so multiple projects can use the same database server. Credentials come from
Fin's system config (``Config.ASSET_*``).
"""
from __future__ import annotations

from fincli.config import Config
from fincli.plugs.base import ContainerSpec
from fincli.plugs.base import FinPlug
from fincli.plugs.base import PlugType
from fincli.plugs.base import PortMapping
from fincli.plugs.base import VolumeMount


class MySQLPlug(FinPlug):
    name = "mysql"
    version = "1.0.0"
    plug_type = PlugType.ASSET
    description = "Shared MySQL database container."

    def asset_specs(self, env) -> list[ContainerSpec]:
        return [
            ContainerSpec(
                service="mysql",
                image="mysql:8.0",
                container_name="fin_mysql",
                environment={
                    "MYSQL_ROOT_PASSWORD": Config.ASSET_PASSWORD,
                    "MYSQL_USER": Config.ASSET_USERNAME,
                    "MYSQL_PASSWORD": Config.ASSET_PASSWORD,
                    "MYSQL_DATABASE": Config.ASSET_DEFAULT_DATABASE,
                },
                ports=[
                    PortMapping(
                        container=3306,
                        host=3306)],
                volumes=[
                    VolumeMount(
                        host="fin_asset_mysql",
                        container="/var/lib/mysql")],
            )]
