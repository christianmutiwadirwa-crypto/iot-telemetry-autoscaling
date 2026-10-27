#!/usr/bin/env bash
# Automated Local Kubernetes (kind) Cluster Setup & Rollout Script (Tasks L17-L22)
set -euo pipefail

CLUSTER_NAME="telemetry-cluster"

echo "=========================================================="
echo "  CITY SEISMIC TELEMETRY: LOCAL KUBERNETES ROLLOUT"
echo "=========================================================="

# 1. Create kind cluster
if kind get clusters 2>/dev/null | grep -q "^${CLUSTER_NAME}$"; then
    echo "[+] kind cluster '${CLUSTER_NAME}' already exists."
else
    echo "[+] Creating 3-node kind cluster '${CLUSTER_NAME}'..."
    kind create cluster --config k8s/kind-config.yaml
fi

# 2. Build local Docker images
echo "[+] Building Ingest API and Processor Docker images..."
docker build -t ingest-api:latest services/ingest-api/
docker build -t processor:latest services/processor/

# 3. Load Docker images into kind nodes
echo "[+] Loading images into kind cluster '${CLUSTER_NAME}'..."
kind load docker-image ingest-api:latest --name "${CLUSTER_NAME}"
kind load docker-image processor:latest --name "${CLUSTER_NAME}"

# 4. Install metrics-server for HPA
echo "[+] Installing metrics-server for HPA..."
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
kubectl patch -n kube-system deployment/metrics-server --type='json' -p='[{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--kubelet-insecure-tls"}]'

# 5. Apply Kubernetes manifests
echo "[+] Applying Kubernetes manifests (k8s/)..."
kubectl apply -k k8s/

# 6. Status Check
echo "[+] Telemetry Pipeline Resources:"
kubectl get pods -n telemetry -o wide
kubectl get svc -n telemetry
kubectl get hpa -n telemetry

echo "[✔] Cluster rollout complete!"
echo "Ingest API: http://localhost:8000/healthz"
echo "RabbitMQ Management: http://localhost:15672 (guest/guest)"
