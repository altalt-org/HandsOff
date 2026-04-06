"""Power control backends (Docker and Kubernetes)."""

from __future__ import annotations

import asyncio

from .config import (
    DEVICE_SERIAL,
    K8S_NAMESPACE,
    K8S_POD_NAME,
    K8S_STATEFULSET,
    POWER_BACKEND,
    REDROID_CONTAINER,
)


class PowerBackend:
    async def restart(self) -> str: ...
    async def power_off(self) -> str: ...
    async def power_on(self) -> str: ...


class DockerBackend(PowerBackend):
    def __init__(self, container_name: str):
        self._container_name = container_name
        self._resolved: str | None = None

    def _client(self):
        import docker
        return docker.DockerClient(base_url="unix:///var/run/docker.sock")

    def _resolve(self):
        """Resolve the container: try the configured name first, then fall back
        to finding the container by its Docker network alias (derived from
        DEVICE_SERIAL hostname).  This handles varying compose project names
        without manual configuration."""
        if self._resolved:
            return self._resolved
        import docker
        client = self._client()
        # Try explicit name first
        try:
            client.containers.get(self._container_name)
            self._resolved = self._container_name
            return self._resolved
        except docker.errors.NotFound:
            pass
        # Fall back: find container whose network alias matches the device hostname
        hostname = DEVICE_SERIAL.split(":")[0]
        for c in client.containers.list(all=True):
            for net_cfg in (c.attrs.get("NetworkSettings", {})
                            .get("Networks", {}).values()):
                aliases = net_cfg.get("Aliases") or []
                if hostname in aliases:
                    self._resolved = c.id
                    return self._resolved
        raise docker.errors.NotFound(
            f"No container found for '{self._container_name}' "
            f"or network alias '{hostname}'"
        )

    async def restart(self) -> str:
        import docker
        try:
            self._client().containers.get(self._resolve()).restart(timeout=10)
            await asyncio.sleep(15)
            return "Device restarted successfully. Call get_device_state to verify."
        except docker.errors.NotFound as e:
            return f"Error: {e}"

    async def power_off(self) -> str:
        import docker
        try:
            self._client().containers.get(self._resolve()).stop(timeout=10)
            return "Device powered off."
        except docker.errors.NotFound as e:
            return f"Error: {e}"

    async def power_on(self) -> str:
        import docker
        try:
            self._client().containers.get(self._resolve()).start()
            await asyncio.sleep(15)
            return "Device powered on. Call get_device_state to verify."
        except docker.errors.NotFound as e:
            return f"Error: {e}"


class KubernetesBackend(PowerBackend):
    def __init__(self, namespace: str, pod_name: str, statefulset: str):
        self._namespace = namespace
        self._pod_name = pod_name
        self._statefulset = statefulset

    def _apis(self):
        try:
            from kubernetes import client as k8s_client, config as k8s_config
        except ImportError:
            raise RuntimeError(
                "POWER_BACKEND=kubernetes requires the 'kubernetes' package: "
                "pip install kubernetes"
            )
        try:
            k8s_config.load_incluster_config()
        except k8s_config.ConfigException:
            k8s_config.load_kube_config()
        return k8s_client.CoreV1Api(), k8s_client.AppsV1Api()

    async def restart(self) -> str:
        core, _ = self._apis()
        core.delete_namespaced_pod(self._pod_name, self._namespace)
        return "Device restarting. Call get_device_state in ~30s to verify."

    async def power_off(self) -> str:
        _, apps = self._apis()
        apps.patch_namespaced_stateful_set_scale(
            self._statefulset, self._namespace, {"spec": {"replicas": 0}}
        )
        return "Device powered off (StatefulSet scaled to 0)."

    async def power_on(self) -> str:
        _, apps = self._apis()
        apps.patch_namespaced_stateful_set_scale(
            self._statefulset, self._namespace, {"spec": {"replicas": 1}}
        )
        return "Device powering on. Call get_device_state in ~30s to verify."


def create_power_backend() -> PowerBackend:
    """Create the appropriate power backend based on config."""
    if POWER_BACKEND == "kubernetes":
        return KubernetesBackend(K8S_NAMESPACE, K8S_POD_NAME, K8S_STATEFULSET)
    return DockerBackend(REDROID_CONTAINER)
