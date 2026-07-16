"""Shared Minio asset plug.

One Minio container shared across every Fin project (fixed name ``fin_minio``),
so multiple projects can use the same object store server. Credentials come from
Fin's system config (``Config.ASSET_*``).
"""
from __future__ import annotations

from pathlib import Path

from fincli.config import Config
from fincli.plugs.base import ContainerSpec
from fincli.plugs.base import FinPlug
from fincli.plugs.base import PlugType
from fincli.plugs.base import PortMapping
from fincli.plugs.base import VolumeMount


class MinioPlug(FinPlug):
    name = "minio"
    version = "1.0.0"
    plug_type = PlugType.ASSET
    description = "Shared Minio Object Storage Container."

    def asset_specs(self, env) -> list[ContainerSpec]:
        return [
            ContainerSpec(
                service="minio",
                image="quay.io/minio/minio",
                container_name="fin_minio",
                environment={
                    "MINIO_ROOT_USER": Config.ASSET_USERNAME,
                    "MINIO_ROOT_PASSWORD": Config.ASSET_PASSWORD,
                },
                command=["server", "/data", "--console-address", ":9001"],
                ports=[
                    PortMapping(container=9000, host=9000),
                    PortMapping(container=9001, host=9001),
                ],
                volumes=[
                    VolumeMount(host=f"{Path.home()}/Documents/minio/data", container="/data")
                ],
                web_exposed=True,
                web_port=9001,
            )]
