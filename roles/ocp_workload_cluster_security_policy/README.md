# ocp_workload_cluster_security_policy

Deploys cluster-level security controls: container registry restrictions and self-provisioner lockout. Network egress policy (AdminNetworkPolicy + EgressFirewall) is handled per-tenant by `ocp4_workload_tenant_namespace` in the `namespaced_workloads` collection.

This role creates one ArgoCD Application (`cluster-security-policy`) pointed at the `cluster-security-policy` chart in this repo. ArgoCD renders the chart into the live cluster objects. `selfHeal` is true. This role finishes when the Application is Healthy and Synced. It does not validate the live objects — `ocp_workload_security_validation` does that, last in the workload list.

`ocp4_workload_openshift_gitops` must run earlier in the workload list. The GitOps controller needs permission to update ClusterRoleBindings and image configuration. Set `ocp4_workload_openshift_gitops_setup_cluster_admin: true`.

## What this chart manages

### Self-provisioner lockout

Empties the subjects on the `self-provisioners` ClusterRoleBinding and sets `autoupdate: false` so the cluster policy controller does not restore it. Students cannot `oc new-project`. GitOps self-heal keeps it locked.

### Allowed registries

Sets `image.config.openshift.io/cluster` to restrict container image pulls to an explicit allowlist. Anything not listed is blocked. Applying this restarts CRI-O on each node (Machine Config Operator cordons each node during the restart).

Default allowlist: `quay.io`, `registry.redhat.io`, `registry.access.redhat.com`, `image-registry.openshift-image-registry.svc:5000`, `docker.io`, `registry-1.docker.io`.

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

ocp_workload_cluster_security_policy_repo_url: https://github.com/rhpds/security.git
ocp_workload_cluster_security_policy_repo_revision: main
ocp_workload_cluster_security_policy_repo_path: cluster-security-policy

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
