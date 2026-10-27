# Azure AKS Runbook & Quota Management (Task Z5)

This runbook specifies the step-by-step procedures for deploying, maintaining, pausing, and destroying the **City-Wide Seismic Telemetry & Autoscaling Cluster** on **Azure Kubernetes Service (AKS)** under an **Azure for Students** subscription.

---

## 1. Subscription & Regional Quotas
* **Subscription Type:** Azure for Students ($100 credit limit).
* **Quota Constraint:** Standard student accounts typically have a regional quota of **4 vCPUs**.
* **Target Node VM Size:** `Standard_B2s` (Burstable series: 2 vCPUs, 4 GiB RAM).
* **Node Count:** 2 nodes ($2 \times 2 = 4\text{ vCPUs}$ max), strictly adhering to the quota.
* **Estimated Cost:**
  * ~$0.0416/hr per VM $\times$ 2 = ~$0.083/hr.
  * Public Load Balancer: ~$0.025/hr.
  * AKS Control Plane: **$0.00 (Free tier)**.
  * Total Hourly Burn Rate: **~$0.11 / hr**.

---

## 2. Quick-Start Commands (Azure CLI)

### 2.1 Authenticate & Set Subscription
```bash
az login
az account show --output table
```

### 2.2 Register AKS Provider & Verify Quota (Task Z3)
```bash
# Register provider
az provider register --namespace Microsoft.ContainerService

# Check vCPU usage in your chosen region (e.g., eastus, westeurope)
az vm list-usage --location eastus --output table | grep -i "standard b"
```

### 2.3 Create Resource Group & AKS Cluster (Tasks Z4, Z22)
```bash
# 1. Create Resource Group
az group create --name telemetry-rg --location eastus

# 2. Create AKS Cluster (2x Standard_B2s, Free Control Plane, no monitoring add-on to save quota)
az aks create \
  --resource-group telemetry-rg \
  --name telemetry-aks \
  --node-count 2 \
  --node-vm-size Standard_B2s \
  --os-disk-size-gb 32 \
  --generate-ssh-keys \
  --tier free

# 3. Connect kubectl
az aks get-credentials --resource-group telemetry-rg --name telemetry-aks --overwrite-existing
kubectl get nodes
```

---

## 3. Sharing Cluster Access with Teammate (Local Owner)
To allow the local track owner to run `kubectl` commands against the cloud cluster:

1. **Export Kubeconfig File:**
   ```bash
   kubectl config view --raw --minify > telemetry-kubeconfig.yaml
   ```
2. **Deliver to Teammate:**
   Send `telemetry-kubeconfig.yaml` securely to your partner.
3. **Partner Usage:**
   ```bash
   export KUBECONFIG=./telemetry-kubeconfig.yaml
   kubectl get pods -n telemetry
   ```

---

## 4. Deploying the Full Telemetry Stack (Task Z23)

```bash
# 1. Install Metrics Server (required for HPA autoscaling)
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml

# 2. Deploy Full Telemetry Pipeline
kubectl apply -k k8s/

# 3. Check Rollout & Public IP (Task Z24)
kubectl get pods -n telemetry -o wide
kubectl get svc -n telemetry ingest-api-service --watch
```
* Once the `EXTERNAL-IP` appears, copy it.
* Point your local simulator dashboard (`http://localhost:8080`) to `http://<EXTERNAL-IP>:8000/api/v1/telemetry`!

---

## 5. Cost Protection: Pause & Teardown (Task Z28)

### To Pause the Cluster (Preserves All Data, Stops Billing for Compute):
```bash
az aks stop --resource-group telemetry-rg --name telemetry-aks
```
* **Cost while stopped:** $0.00 for VMs (only ~$0.05/day for static disk storage).

### To Resume the Cluster:
```bash
az aks start --resource-group telemetry-rg --name telemetry-aks
```

### Final Teardown (Destroys Everything When Demos are Done):
```bash
az group delete --name telemetry-rg --yes --no-wait
```
* Completely removes all resources and prevents any future charges.
