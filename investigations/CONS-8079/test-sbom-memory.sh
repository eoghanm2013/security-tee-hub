#!/bin/bash
set -e

# Test script to measure Datadog Agent memory consumption with SBOM settings
# Related to: CONS-8079 - AKS memory high after enabling uncompressedLayersSupport

CLUSTER_NAME="sbom-memory-test"
NAMESPACE="datadog"
RESULTS_FILE="./memory-test-results.txt"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

# Check prerequisites
check_prereqs() {
    log "Checking prerequisites..."
    
    if ! command -v kind &> /dev/null; then
        error "kind not found. Install with: brew install kind"
        exit 1
    fi
    
    if ! command -v kubectl &> /dev/null; then
        error "kubectl not found. Install with: brew install kubectl"
        exit 1
    fi
    
    if ! command -v helm &> /dev/null; then
        error "helm not found. Install with: brew install helm"
        exit 1
    fi
    
    if [ -z "$DD_API_KEY" ]; then
        error "DD_API_KEY environment variable not set"
        exit 1
    fi
    
    log "All prerequisites met ✓"
}

# Create kind cluster
create_cluster() {
    log "Creating kind cluster: $CLUSTER_NAME"
    
    if kind get clusters | grep -q "^${CLUSTER_NAME}$"; then
        warn "Cluster $CLUSTER_NAME already exists. Deleting..."
        kind delete cluster --name $CLUSTER_NAME
    fi
    
    kind create cluster --name $CLUSTER_NAME --config - <<EOF
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
nodes:
- role: control-plane
- role: worker
- role: worker
EOF
    
    log "Cluster created successfully ✓"
}

# Add Datadog Helm repo
setup_helm() {
    log "Setting up Helm repository..."
    helm repo add datadog https://helm.datadoghq.com
    helm repo update
    log "Helm repository ready ✓"
}

# Wait for agent pods to be ready
wait_for_agent() {
    log "Waiting for Datadog Agent pods to be ready..."
    kubectl wait --for=condition=ready pod -l app=datadog -n $NAMESPACE --timeout=300s
    log "Agent pods are ready ✓"
}

# Get memory usage for agent pods
get_memory_usage() {
    local test_name=$1
    
    log "Measuring memory usage for: $test_name"
    sleep 30 # Let things stabilize
    
    # Get memory from kubectl top
    local memory_output=$(kubectl top pods -n $NAMESPACE 2>/dev/null | grep datadog)
    
    if [ -z "$memory_output" ]; then
        warn "Could not get memory metrics from kubectl top (metrics-server may not be running)"
        # Fallback: check container memory from cgroup
        local agent_pod=$(kubectl get pods -n $NAMESPACE -l app=datadog -o jsonpath='{.items[0].metadata.name}')
        log "Checking memory via agent container on pod: $agent_pod"
        
        # Get RSS memory from agent
        local rss_memory=$(kubectl exec -n $NAMESPACE $agent_pod -c agent -- sh -c "cat /proc/self/status | grep VmRSS" 2>/dev/null || echo "Unable to get RSS")
        
        echo "=== $test_name ===" | tee -a $RESULTS_FILE
        echo "Timestamp: $(date)" | tee -a $RESULTS_FILE
        echo "Agent Pod: $agent_pod" | tee -a $RESULTS_FILE
        echo "RSS Memory: $rss_memory" | tee -a $RESULTS_FILE
        echo "" | tee -a $RESULTS_FILE
    else
        echo "=== $test_name ===" | tee -a $RESULTS_FILE
        echo "Timestamp: $(date)" | tee -a $RESULTS_FILE
        echo "$memory_output" | tee -a $RESULTS_FILE
        echo "" | tee -a $RESULTS_FILE
    fi
    
    # Also check agent status for SBOM info
    local agent_pod=$(kubectl get pods -n $NAMESPACE -l app=datadog -o jsonpath='{.items[0].metadata.name}')
    log "Getting SBOM check status from pod: $agent_pod"
    kubectl exec -n $NAMESPACE $agent_pod -c agent -- agent status | grep -A 20 "sbom" | tee -a $RESULTS_FILE || true
    echo "" | tee -a $RESULTS_FILE
}

# Deploy Datadog agent with specific config
deploy_agent() {
    local test_name=$1
    local sbom_enabled=$2
    local uncompressed_layers=$3
    
    log "Deploying Datadog Agent: $test_name"
    log "  SBOM enabled: $sbom_enabled"
    log "  Uncompressed layers support: $uncompressed_layers"
    
    kubectl create namespace $NAMESPACE 2>/dev/null || true
    
    helm upgrade --install datadog datadog/datadog \
        --namespace $NAMESPACE \
        --set datadog.apiKey=$DD_API_KEY \
        --set datadog.site=datadoghq.com \
        --set datadog.clusterName="sbom-test-local" \
        --set datadog.sbom.containerImage.enabled=$sbom_enabled \
        --set datadog.sbom.containerImage.uncompressedLayersSupport=$uncompressed_layers \
        --set datadog.logs.enabled=false \
        --set datadog.apm.enabled=false \
        --set datadog.processAgent.enabled=false \
        --set agents.useHostNetwork=false \
        --wait --timeout 8m
    
    wait_for_agent
    log "Agent deployed successfully ✓"
}

# Run test sequence
run_tests() {
    log "Starting memory consumption tests..."
    echo "# SBOM Memory Consumption Test Results" > $RESULTS_FILE
    echo "# Related to: CONS-8079" >> $RESULTS_FILE
    echo "# Date: $(date)" >> $RESULTS_FILE
    echo "" >> $RESULTS_FILE
    
    # Test 1: Baseline - SBOM disabled
    log "TEST 1: Baseline (SBOM disabled)"
    deploy_agent "Test 1: SBOM Disabled" "false" "false"
    sleep 120  # Wait 2 mins for baseline
    get_memory_usage "Test 1: SBOM Disabled (Baseline)"
    
    # Test 2: SBOM enabled WITHOUT uncompressedLayersSupport
    log "TEST 2: SBOM enabled, uncompressedLayersSupport=false"
    deploy_agent "Test 2: SBOM Basic" "true" "false"
    sleep 180  # Wait 3 mins for SBOM to run
    get_memory_usage "Test 2: SBOM Enabled (uncompressedLayersSupport=false)"
    
    # Test 3: SBOM enabled WITH uncompressedLayersSupport (the problematic one)
    log "TEST 3: SBOM enabled, uncompressedLayersSupport=true"
    deploy_agent "Test 3: SBOM with uncompressedLayersSupport" "true" "true"
    sleep 300  # Wait 5 mins for scanning with layer extraction
    get_memory_usage "Test 3: SBOM Enabled (uncompressedLayersSupport=true) - PROBLEMATIC"
    
    log "All tests completed! Results saved to: $RESULTS_FILE"
}

# Cleanup
cleanup() {
    log "Cleaning up..."
    if [ "$1" != "--no-delete" ]; then
        kind delete cluster --name $CLUSTER_NAME
        log "Cluster deleted ✓"
    else
        warn "Cluster kept for manual inspection. Delete with: kind delete cluster --name $CLUSTER_NAME"
    fi
}

# Main execution
main() {
    log "Starting SBOM Memory Test for CONS-8079"
    
    check_prereqs
    create_cluster
    setup_helm
    run_tests
    
    log "Test complete! Review results in: $RESULTS_FILE"
    
    # Ask user if they want to keep cluster
    echo ""
    read -p "Keep cluster for manual inspection? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        cleanup
    else
        cleanup --no-delete
        log "To inspect the cluster:"
        log "  kubectl get pods -n $NAMESPACE"
        log "  kubectl top pods -n $NAMESPACE"
        log "  kubectl exec -it <pod-name> -n $NAMESPACE -c agent -- agent status"
    fi
}

# Handle Ctrl+C
trap 'error "Script interrupted. Cleaning up..."; cleanup; exit 1' INT

# Run main
main


