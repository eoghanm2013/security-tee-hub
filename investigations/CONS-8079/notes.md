# CONS-8079: AKS Memory High After Enabling SBOM Uncompressed Layers Support

**Status:** TEE - In Progress  
**Assignee:** Mathieu Colin  
**Reporter:** Luan Spano  
**Created:** 2026-02-12  
**Customer:** Bots (Org: 1200054929, Tier 2, Pro)  
**Related Zendesk:** [2484087](https://datadog.zendesk.com/agent/tickets/2484087)

## TL;DR

Customer experiencing **350-400 MiB memory increase** in AKS agent pods after enabling `datadog.sbom.containerImage.uncompressedLayersSupport: true`, which is required for CSM Vulnerability scanning on AKS. This is a **known pattern** with SBOM scanning on managed Kubernetes platforms (AKS, EKS, GKE) where containerd discards uncompressed layers by default.

**Root Cause:** The `uncompressedLayersSupport` feature requires mounting host containerd directories and extracting compressed layers at scan time, significantly increasing cache and kernel memory usage (not RSS memory from the agent process itself).

**Status:** Escalated to Security team (moved from Containers). This appears to be **expected behavior** given the feature's architecture, but memory consumption may be higher than documented/expected.

---

## Problem Statement

### Symptoms
- Agent memory usage climbs from ~170 MiB to ~680 MiB (400+ MiB increase)
- Memory does not get released after increase
- Occurs specifically when `datadog.sbom.containerImage.uncompressedLayersSupport: true` is enabled
- Agent pod resource limits are set but appear ineffective at preventing the climb
- Affects AKS cluster: `aks-bots-prod-uks-green`

### Timeline
1. **Dec 23, 2025:** Customer disabled `uncompressedLayersSupport` due to memory concerns (ticket 2356717)
2. **Jan 21, 2026:** Customer re-enabled it because CSM Vulnerabilities stopped reporting (ticket 2483027)
3. **Feb 9, 2026:** Memory usage high again, escalated to CONS-8079

### Environment
- **Platform:** Azure AKS
- **Agent Version:** 7.73.0
- **Helm Chart:** 3.156.1
- **Cluster:** aks-bots-prod-uks-green
- **Namespace:** datadog
- **Configuration:**
  ```yaml
  datadog:
    sbom:
      containerImage:
        enabled: true
        uncompressedLayersSupport: true
        analyzers:
          - os
          - languages
        containerExclude: |
          kube_namespace:^kube-system$
          image:^mcr.microsoft.com/aks/.*$
          image:^mcr.microsoft.com/oss/.*$
          image:^mcr.microsoft.com/azuredefender/.*$
  ```

---

## Investigation

### Pattern Recognition: This is a Known Issue

**Similar Cases:**
1. **CONS-7954** (Dec 2024): Bots customer, same 680 MiB memory usage with SBOM + `uncompressedLayersSupport`
2. **ZD 2356717** (earlier): Same customer, resolved by disabling `uncompressedLayersSupport`
3. **ZD 2483027** (Jan 2026): CSM Vulnerabilities stopped when disabled, had to re-enable

**Pattern:** This is a **cyclical issue** where customers must choose between:
- **Option A:** Enable `uncompressedLayersSupport` → Get CSM Vulnerabilities → High memory usage
- **Option B:** Disable `uncompressedLayersSupport` → Normal memory → No CSM Vulnerabilities

### Technical Analysis

#### Why This Happens on AKS/EKS/GKE

From [SBOM Collection KB](https://datadoghq.atlassian.net/wiki/spaces/TS/pages/3249702351):

> AKS (like EKS and minikube) configures containerd to **discard uncompressed layers by default** (`discard_unpacked_layers=true`). The `uncompressedLayersSupport: true` setting works around this limitation, but it requires additional memory to process the compressed layers during scanning.

**What `uncompressedLayersSupport` Does:**
1. Mounts host containerd snapshotter directories (`/host/var/lib/containerd/io.containerd.snapshotter.v1.overlayfs/`)
2. Extracts compressed image layers at scan time (instead of using pre-extracted layers)
3. Adds `SYS_ADMIN` capability to agent container for mounting operations
4. Significantly increases **cache and kernel memory** (not RSS memory from agent process)

#### Memory Profile Analysis

From flare analysis (CONS-7954 investigation by Patrick Liang):

> The profiles don't show SBOM using all that much RSS memory. The interesting part is the **cache and kernel memory**, maybe due to them setting `uncompressedLayersSupport: true`.

**Key Finding:** Memory increase is NOT from the agent process itself, but from:
- **Cache memory:** Filesystem cache for extracted layers
- **Kernel memory:** Kernel-level memory for mount operations and filesystem handling

This explains why:
- Memory profiles show low SBOM process usage
- Container memory limits don't prevent the climb (kernel memory is outside container limits)
- Memory doesn't get released (kernel caches persist)

### SBOM Check Status

From flare (pod consuming 680 MiB):

```
sbom status:
  Instance ID: sbom [OK]
  Long Running Check: true
  Configuration Source: file:/etc/datadog-agent/conf.d/sbom.d/conf.yaml.default[0]
  Total container-sbom: 76
  Total Service Checks: 0
```

**Observations:**
- SBOM check is running successfully
- 76 container SBOMs generated
- No errors in agent logs (just normal "Running check" / "Done running check")
- Process appears healthy, just consuming more memory than expected

### Attempted Mitigations (Customer Tried)

1. **Resource limits:** Set but ineffective (kernel memory outside container limits)
2. **`DD_SBOM_CACHE_CLEAN_INTERVAL: 30m`:** No improvement
3. **`overlayFSDirectScan: true`:** Customer tried before, got errors:
   ```
   ERROR | SBOM generation failed for image: unable to extract layers from overlayfs mounts
   ```
   Re-enabled but no memory improvement

### Proposed Solutions (From Mathieu Colin - Containers TEE)

#### Solution 1: Disable `uncompressedLayersSupport` + Modify Containerd Config

**Recommendation:** Set `discard_unpacked_layers=false` in containerd configuration, then disable `uncompressedLayersSupport`.

**Problem:** This is **outside Datadog's scope** and not feasible on managed AKS:
- AKS manages containerd configuration
- No documented way to modify `discard_unpacked_layers` on AKS nodes
- Microsoft doc on [node customization](https://learn.microsoft.com/en-us/azure/aks/custom-node-configuration) doesn't mention containerd config

**Customer Response:**
> I don't think that modifying containerd config will be possible for users of most managed Kubernetes platforms to be honest!

#### Solution 2: Use `overlayFSDirectScan` (Experimental)

**Configuration:**
```yaml
datadog:
  sbom:
    containerImage:
      enabled: true
      uncompressedLayersSupport: true
      overlayFSDirectScan: true
```

**Status:** Customer tried this, got errors. Re-enabled but no memory improvement.

**Note:** This is marked as "experimental" in helm chart and may have compatibility issues with certain image types or containerd configurations.

#### Solution 3: Adjust Resource Requests/Limits

**Proposed (from ZD 2484087):**
```yaml
resources:
  requests:
    memory: "250Mi"  # Reduced from typical 500Mi
    cpu: "100m"
  limits:
    memory: "512Mi"
    cpu: "200m"
```

**Problem:** This doesn't address root cause (kernel memory), just masks the symptom. May cause OOMKills if actual usage exceeds limits.

#### Solution 4: Reduce Disk Space Requirement

**Configuration:**
```yaml
env:
  - name: DD_SBOM_CONTAINER_IMAGE_MIN_AVAILABLE_DISK
    value: "500Mi"  # Default is 1GB
```

**Relevance:** Only helps if disk space is the constraint. Customer's issue is memory, not disk.

---

## Root Cause Assessment

### Is This a Bug or Expected Behavior?

**Containers Team Assessment (Mathieu Colin):**
> I'm not sure that this memory increase is unexpected given the feature you have enabled.

**Security Team Assessment:** Pending (escalation just moved to Security)

### Expected vs Actual Memory Usage

**Expected (per docs):**
- Docs mention "additional memory" but don't quantify
- No specific guidance on expected memory increase
- Troubleshooting guide focuses on disk space, not memory

**Actual:**
- **350-400 MiB increase** (170 MiB → 680 MiB)
- **Persistent** (doesn't release after scans)
- **Affects production workloads** (customer considering disabling agent)

**Customer Sentiment:**
> I think that the memory usage is too high for what the feature purports to be doing: scanning hourly or when new images are introduced. But, if it can't be helped then we should close this ticket.

---

## Architectural Considerations

### Why `uncompressedLayersSupport` Requires High Memory

From [helm chart template](https://github.com/DataDog/helm-charts/blob/main/charts/datadog/templates/_container-agent.yaml):

```yaml
{{- if .Values.datadog.sbom.containerImage.uncompressedLayersSupport }}
  {{- if .Values.datadog.sbom.containerImage.overlayFSDirectScan }}
    - name: DD_SBOM_CONTAINER_IMAGE_OVERLAYFS_DIRECT_SCAN
      value: "true"
  {{- else }}
    - name: DD_SBOM_CONTAINER_IMAGE_USE_MOUNT
      value: "true"
  {{- end }}
{{- end }}
```

**When `uncompressedLayersSupport` is enabled:**
1. Adds `SYS_ADMIN` capability (for mounting)
2. Mounts `/host/var/lib/containerd/` into agent container
3. Agent extracts compressed layers to temporary location
4. Scans extracted layers
5. Kernel caches extracted data (cache memory)
6. Mount operations consume kernel memory

**Alternative (when containerd has uncompressed layers):**
1. No `SYS_ADMIN` needed
2. No host mounts needed
3. Scans pre-extracted layers directly
4. Minimal memory overhead

### Comparison: Memory Usage Patterns

| Scenario | Memory Usage | CSM Vulnerabilities | Notes |
|---|---|---|---|
| SBOM disabled | ~170 MiB | ❌ No | Baseline |
| SBOM + `uncompressedLayersSupport: false` | ~170 MiB | ❌ No | Scans fail on AKS |
| SBOM + `uncompressedLayersSupport: true` | ~680 MiB | ✅ Yes | 400 MiB increase |
| SBOM + `overlayFSDirectScan: true` | Unknown | ⚠️ Errors | Experimental, inconsistent |

---

## Recommendations

### For Customer (Short-term)

**Option 1: Accept Memory Increase (Recommended by TEE)**
- This appears to be expected behavior for the feature
- Increase agent memory limits to accommodate:
  ```yaml
  resources:
    requests:
      memory: "700Mi"
    limits:
      memory: "1Gi"
  ```
- Monitor for OOMKills and adjust as needed
- **Risk:** Higher memory footprint across all agent pods

**Option 2: Disable SBOM Scanning**
- Set `datadog.sbom.containerImage.enabled: false`
- Lose CSM Vulnerability scanning capability
- Return to ~170 MiB memory usage
- **Risk:** No container vulnerability visibility

**Option 3: Selective SBOM Scanning**
- Use `containerInclude`/`containerExclude` to scan only critical images
- May reduce number of concurrent scans and memory pressure
- **Example:**
  ```yaml
  datadog:
    sbom:
      containerImage:
        containerInclude: "image:^your-registry/critical-app.*$"
  ```

### For Engineering (Long-term)

**Potential Improvements:**
1. **Document expected memory usage** for `uncompressedLayersSupport` feature
2. **Implement memory-efficient layer extraction** (streaming, on-demand cleanup)
3. **Add configuration for cache size limits** (`DD_SBOM_CACHE_MAX_SIZE`?)
4. **Investigate `overlayFSDirectScan` reliability** on AKS/EKS/GKE
5. **Consider alternative SBOM collection methods** that don't require layer extraction

**Feature Request Candidates:**
- Memory usage optimization for `uncompressedLayersSupport`
- Configurable cache cleanup intervals/sizes
- Better documentation on memory requirements
- Alternative scanning methods for managed K8s platforms

---

## Next Steps

### Immediate Actions
1. **Security team assessment:** Confirm if 400 MiB increase is expected/acceptable
2. **Customer decision:** Accept memory increase vs disable feature
3. **Documentation update:** Add memory usage guidance to troubleshooting docs

### Follow-up Questions for Security Team
1. Is 350-400 MiB memory increase expected for `uncompressedLayersSupport`?
2. Are there plans to optimize memory usage for this feature?
3. Should we document expected memory requirements in public docs?
4. Is `overlayFSDirectScan` production-ready or still experimental?

---

## References

### Internal Documentation
- [SBOM Collection of Container Image](https://datadoghq.atlassian.net/wiki/spaces/TS/pages/3249702351)
- [CSM Vuln General Troubleshooting](https://datadoghq.atlassian.net/wiki/spaces/TS/pages/4145577988)
- [CONS-7954](https://datadoghq.atlassian.net/browse/CONS-7954) - Similar memory issue

### Public Documentation
- [Troubleshooting Cloud Security Vulnerabilities](https://docs.datadoghq.com/security/cloud_security_management/troubleshooting/vulnerabilities/)
- [Uncompressed Container Image Layers](https://docs.datadoghq.com/security/cloud_security_management/troubleshooting/vulnerabilities/#uncompressed-container-image-layers)

### Related Tickets
- **ZD 2484087** - Current ticket (AKS memory high)
- **ZD 2356717** - Previous memory issue (resolved by disabling feature)
- **ZD 2483027** - CSM Vulnerabilities stopped (required re-enabling feature)
- **CONS-7954** - Similar JIRA escalation (Dec 2024)

### Slack Threads
- [#support-containers thread](https://dd.slack.com/archives/C4UD9L724/p1770726229154759) - Initial escalation discussion

---

## Lessons Learned

### Pattern: Feature vs Resource Trade-off
This is a classic case where enabling a security feature (CSM Vulnerabilities) requires significant resource overhead on managed Kubernetes platforms. The architectural limitation (containerd discarding uncompressed layers) forces a workaround that has substantial memory costs.

### Customer Communication
- Be transparent about trade-offs
- Don't promise memory reduction if architecture doesn't support it
- Provide clear options with pros/cons
- Escalate to product team for long-term solutions

### Investigation Approach
- Check for similar historical cases first (found CONS-7954, ZD 2356717)
- Understand the underlying architecture (containerd behavior, kernel memory)
- Distinguish between bugs and expected behavior
- Don't recommend config changes that are infeasible on managed platforms


