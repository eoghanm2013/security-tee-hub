# SBOM Memory Test - CONS-8079

## Purpose
Test locally to measure the memory impact of enabling `datadog.sbom.containerImage.uncompressedLayersSupport` on the Datadog Agent.

## What This Tests

The script runs 3 sequential tests on a local kind cluster:

1. **Baseline** - Agent with SBOM completely disabled
2. **SBOM Basic** - Agent with SBOM enabled, `uncompressedLayersSupport=false`
3. **SBOM Full** - Agent with SBOM enabled, `uncompressedLayersSupport=true` (**the problematic setting**)

Each test:
- Deploys the agent via Helm
- Waits for pods to stabilize
- Measures memory consumption
- Logs SBOM check status

## Prerequisites

```bash
# Install tools (macOS)
brew install kind kubectl helm

# Set your DD API key
export DD_API_KEY="your_api_key_here"
```

## Run Test

```bash
cd /Users/eoghan.mellott/security-tee-hub/investigations/CONS-8079
./test-sbom-memory.sh
```

**Expected runtime:** ~15-20 minutes

## What to Expect

- Kind cluster will be created with 3 nodes (1 control plane, 2 workers)
- Agent will be deployed 3 times with different configs
- Memory measurements will be captured in `memory-test-results.txt`
- At the end, you'll be asked if you want to keep the cluster for manual inspection

## Manual Inspection (if you keep cluster)

```bash
# Check pods
kubectl get pods -n datadog

# See memory usage (requires metrics-server, may not work in kind)
kubectl top pods -n datadog

# Check agent status
kubectl exec -it <pod-name> -n datadog -c agent -- agent status

# Check SBOM specifically
kubectl exec -it <pod-name> -n datadog -c agent -- agent status | grep -A 20 sbom

# Get logs
kubectl logs -n datadog <pod-name> -c agent | grep -i sbom
```

## Cleanup

If you kept the cluster:
```bash
kind delete cluster --name sbom-memory-test
```

## Expected Results

Based on CONS-8079 and similar tickets:
- **Baseline (no SBOM):** ~150-200 MiB
- **SBOM without uncompressed layers:** ~200-250 MiB
- **SBOM with uncompressed layers:** ~500-650 MiB (**+350-400 MiB increase**)

## Notes

- This uses a local kind cluster, not real AKS/EKS
- Memory consumption may differ from production environments
- The key metric is the **delta** between Test 2 and Test 3
- If `kubectl top` doesn't work (no metrics-server), we fall back to reading `/proc/self/status` from inside the container


