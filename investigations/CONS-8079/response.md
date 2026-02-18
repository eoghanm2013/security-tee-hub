# Response for Customer (Bots - Ticket 2484087)

## Summary

The **350-400 MiB memory increase** you're seeing with `datadog.sbom.containerImage.uncompressedLayersSupport: true` is **expected behavior** based on how this feature works on managed Kubernetes platforms like AKS.

**Why this happens:** AKS configures containerd to discard uncompressed image layers by default. When you enable `uncompressedLayersSupport`, the agent must extract and mount compressed layers at scan time, which significantly increases **cache and kernel memory** (not the agent process itself). This memory persists because the kernel caches the extracted layer data.

## Your Options

### ✅ Option 1: Accept the Memory Increase (Recommended)

**What to do:**
Increase your agent memory limits to accommodate the SBOM scanning overhead:

```yaml
agents:
  containers:
    agent:
      resources:
        requests:
          memory: "700Mi"
        limits:
          memory: "1Gi"
```

**Pros:**
- Keep CSM Vulnerability scanning enabled
- No functionality loss
- Straightforward configuration

**Cons:**
- Higher memory footprint across all agent pods
- Increased infrastructure costs

**Risk Level:** 🟢 **LOW** - This is a resource allocation change, easily reversible

---

### Option 2: Selective SBOM Scanning

**What to do:**
Scan only your critical application images instead of all images:

```yaml
datadog:
  sbom:
    containerImage:
      enabled: true
      uncompressedLayersSupport: true
      containerInclude: "image:^your-registry/critical-app.*$"
      containerExclude: |
        kube_namespace:^kube-system$
        image:^mcr.microsoft.com/.*$
```

**Pros:**
- Reduce number of concurrent scans
- Lower memory pressure
- Still get vulnerability data for important workloads

**Cons:**
- Partial visibility (only scanned images)
- Requires careful filter configuration

**Risk Level:** 🟡 **MEDIUM** - May miss vulnerabilities in excluded images

---

### Option 3: Disable SBOM Scanning

**What to do:**
```yaml
datadog:
  sbom:
    containerImage:
      enabled: false
```

**Pros:**
- Return to ~170 MiB memory usage
- No memory concerns

**Cons:**
- **Lose all CSM Vulnerability scanning**
- No container image vulnerability visibility

**Risk Level:** 🔴 **HIGH** - Loss of security visibility

---

## Why Other Solutions Won't Work

### ❌ Modifying Containerd Configuration
The ideal solution would be to set `discard_unpacked_layers=false` in containerd, which would eliminate the need for `uncompressedLayersSupport`. However, **this is not possible on managed AKS** because Microsoft controls the containerd configuration and doesn't provide a way to modify this setting.

### ⚠️ overlayFSDirectScan (Experimental)
You mentioned trying `overlayFSDirectScan: true`, which is an experimental alternative. Based on your results (errors and no memory improvement), this doesn't appear to be a viable solution for your environment at this time.

### ❌ Reducing Resource Limits
Setting lower memory limits won't prevent the kernel memory usage. It will just cause OOMKills when the agent hits the limit, disrupting your monitoring.

---

## What We're Doing

We've escalated this to the **Security product team** to:
1. Confirm if 350-400 MiB is the expected memory overhead
2. Explore potential optimizations for future releases
3. Update documentation with clear memory requirements

---

## Recommendation

**We recommend Option 1** (accept the memory increase) because:
- CSM Vulnerability scanning provides important security visibility
- The memory increase, while significant, is **expected behavior** for this feature on AKS
- It's the most straightforward and lowest-risk solution
- You can easily revert if needed

**Next step:** Let us know which option works best for your environment, and we'll help you implement it.

---

## Technical Details (if interested)

**Why the memory increase happens:**

When `uncompressedLayersSupport` is enabled:
1. Agent mounts host containerd directories (`/host/var/lib/containerd/`)
2. Extracts compressed image layers to scan them
3. Kernel caches the extracted layer data (**cache memory**)
4. Mount operations consume **kernel memory**
5. This memory is outside the agent container's RSS memory, which is why profiles show low SBOM process usage

**Why it doesn't release:**
Kernel caches persist to optimize future access. The kernel will only release this memory under memory pressure, not proactively.

**Why containerd discards layers on AKS:**
Managed Kubernetes platforms (AKS, EKS, GKE) optimize for storage efficiency by configuring containerd with `discard_unpacked_layers=true`. This saves disk space but makes SBOM scanning require the workaround that causes higher memory usage.


