# ocp_workload_cluster_security_policy

Deploys an AdminNetworkPolicy that controls egress from tenant namespaces. Self-provisioning, container registry restrictions, and all other cluster-level security controls are part of the same Helm chart.

This role creates one ArgoCD Application (`cluster-security-policy`) pointed at the `cluster-security-policy` chart in this repo. ArgoCD renders the chart into the live cluster objects. `selfHeal` is true. This role finishes when the Application is Healthy and Synced. It does not validate the live objects — `ocp_workload_security_validation` does that, last in the workload list.

`ocp4_workload_openshift_gitops` must run earlier in the workload list. The GitOps controller needs permission to create AdminNetworkPolicies and update ClusterRoleBindings. Set `ocp4_workload_openshift_gitops_setup_cluster_admin: true`.

## How the egress policy works

The chart renders an AdminNetworkPolicy called `tenant-egress`. It applies to every namespace with the label `demo.redhat.com/tenant-uuid` — which includes every student namespace and every Showroom namespace.

The policy has one ingress rule and several egress rules. Egress rules are evaluated top to bottom, first match wins.

### Ingress (traffic coming IN to student pods)

| Rule | Target | Why |
|------|--------|-----|
| `allow-from-ingress` | Namespaces with the `policy-group.network.openshift.io/ingress` label | Router pods can reach student pods so that routes serve traffic |

### Egress (traffic going OUT from student pods)

| Rule | Target | Port | Why |
|------|--------|------|-----|
| `allow-dns` | Pods in `openshift-dns` namespace | 53, 5353 (UDP+TCP) | DNS resolution |
| `allow-api` | Control-plane nodes | 6443 | `oc` commands, API calls |
| `allow-ingress-routes` | All nodes | 443 | OAuth login, routes (console, Gitea, student apps) |
| `allow-image-registry` | Pods in `openshift-image-registry` namespace | 5000 | Image pull and push |
| `allow-kubernetes-api-svc` | Pods in `default` namespace | 443 | In-cluster API access via `kubernetes.default.svc` |
| `allow-to-*` | Pods in namespaces from `allowNamespaces` | any | Additional namespaces a specific lab needs |
| `allow-extra-cidrs` | CIDRs from `extraEgressCIDRs` | any | External addresses a lab needs |
| `deny-outside` | `0.0.0.0/0` and `::/0` | any | Block everything else |

Rule order matters. Anything that doesn't match a prior rule hits `deny-outside` and is silently dropped (the student sees a timeout, not a connection refused).

The image registry and `kubernetes.default.svc` rules are port-restricted. The `allowNamespaces` rules are not — they allow any port to any pod in the listed namespace, so use them only when you know what the namespace exposes.

### How the nodes selectors work

In the CNV environment, the OpenShift cluster runs as VMs. The API and ingress each have a keepalived VIP — a floating IP that lives on one of the nodes:

- `api.cluster-xxxxx...` resolves to the API VIP (hosted on a control-plane node)
- `*.apps.cluster-xxxxx...` resolves to the ingress VIP (hosted on a worker or control-plane node)

These VIPs are not pod IPs or service ClusterIPs. They are addresses on the VM network. But OVN (the cluster's network engine) recognizes that traffic to a VIP hosted on a node is traffic "to that node." A `nodes` selector in the ANP matches VIP traffic.

That is why `allow-api` uses a `nodes` selector targeting control-plane nodes on port 6443, and why `allow-ingress-routes` uses a `nodes` selector targeting all nodes on port 443. Both work because OVN matches the keepalived VIP to the hosting node.

### The hairpin

When a pod accesses a route on the same cluster, the traffic does not stay inside the overlay network. It exits OVN, hits the keepalived VIP on the host network, goes through haproxy, and comes back into the cluster through the ingress controller:

```
pod → OVN → node NIC → host bridge → keepalived VIP → haproxy → node NIC → OVN → router pod → app pod
```

The ANP evaluates the packet when it first leaves the pod. At that point the destination is the VIP address, not the app pod's address. The VIP address falls into `0.0.0.0/0` unless an earlier rule matches it. That is why `allow-ingress-routes` exists — without it, every route on the cluster is unreachable from tenant pods.

### Why we do not use extraEgressCIDRs for VIPs

An earlier approach resolved the API and ingress hostnames at deploy time using `community.general.dig` and added the IPs to `extraEgressCIDRs`. This does not work because of split-horizon DNS: the deployer (which runs the Ansible role) resolves from outside the cluster and gets the public IP. Pods inside the cluster resolve to the internal keepalived VIP. The CIDR from the deployer never matches the traffic pods actually send.

`extraEgressCIDRs` remains in the chart for labs that genuinely need to reach a specific external address, but it is not populated automatically.

### What a student experiences

**`oc login` from the Showroom terminal:**

1. DNS lookup for `api.cluster-xxxxx...` → CoreDNS in `openshift-dns` → allowed by `allow-dns` → returns API VIP
2. Connect to API VIP on port 6443 → allowed by `allow-api` → API returns OAuth URL
3. DNS lookup for `oauth-openshift.apps.cluster-xxxxx...` → allowed by `allow-dns` → returns ingress VIP
4. Connect to ingress VIP on port 443 → allowed by `allow-ingress-routes` → OAuth validates credentials → login succeeds

**Accessing a route (console, Gitea, a student's own deployed app):**

1. DNS resolves `*.apps.cluster-xxxxx...` → ingress VIP (same IP for all routes)
2. Connect to ingress VIP on port 443 → allowed by `allow-ingress-routes`
3. VIP forwards to a router pod, which routes to the target app pod → works

**`curl google.com`:**

1. DNS resolves → allowed by `allow-dns` → returns Google's IP
2. Connect to Google's IP → does not match any allow rule → hits `deny-outside` → silently dropped → timeout

**`oc new-project`:**

1. API call to API VIP on port 6443 → allowed by `allow-api`
2. API checks the `self-provisioners` ClusterRoleBinding → subjects list is empty → 403 Forbidden

## Role variables

| Variable | Default | Description |
|---|---|---|
| `ocp_workload_cluster_security_policy_repo_url` | `https://github.com/rhpds/security.git` | Git repo of the chart |
| `ocp_workload_cluster_security_policy_repo_revision` | `main` | Git revision ArgoCD tracks |
| `ocp_workload_cluster_security_policy_repo_path` | `cluster-security-policy` | Path of the chart |
| `ocp_workload_cluster_security_policy_application_name` | `cluster-security-policy` | Application name |
| `ocp_workload_cluster_security_policy_namespace` | `openshift-gitops` | Namespace of the Application |
| `ocp_workload_cluster_security_policy_project` | `default` | ArgoCD project |
| `ocp_workload_cluster_security_policy_helm_values` | `{}` | Helm values merged onto `cluster-security-policy/values.yaml` |
| `ocp_workload_cluster_security_policy_health_retries` | `60` | How many 10-second waits for Healthy and Synced |

## Catalog item example

```yaml
workloads:
  - agnosticd.core_workloads.ocp4_workload_openshift_gitops
  - rhpds.security.ocp_workload_cluster_security_policy

ocp_workload_cluster_security_policy_helm_values:
  selfProvisioner:
    enabled: false
  allowedRegistries:
    - quay.io
    - registry.redhat.io
    - registry.access.redhat.com
    - image-registry.openshift-image-registry.svc:5000
    - docker.io
    - registry-1.docker.io
```
