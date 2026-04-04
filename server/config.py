"""Environment variables and constants."""

from __future__ import annotations

import os

DEVICE_SERIAL = os.environ.get("DEVICE_SERIAL", "localhost:5555")
USE_TCP = os.environ.get("DROIDRUN_USE_TCP", "true").lower() in ("1", "true", "yes")
PORT = int(os.environ.get("PORT", "8000"))
REDROID_CONTAINER = os.environ.get("REDROID_CONTAINER", "redroid")

# Power backend: "docker" (default) uses docker.sock; "kubernetes" uses K8s API.
# Set POWER_BACKEND=kubernetes when running as an EKS sidecar.
# Requires: pip install kubernetes  (not listed in requirements.txt — optional dep)
POWER_BACKEND = os.environ.get("POWER_BACKEND", "docker")
K8S_NAMESPACE = os.environ.get("K8S_NAMESPACE", "default")
K8S_POD_NAME = os.environ.get("K8S_POD_NAME", "redroid-0")
K8S_STATEFULSET = os.environ.get("K8S_STATEFULSET", "redroid")
