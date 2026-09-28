# ocp_workload_cluster_security_policy

Cluster catalog item workload. It does not install OpenShift GitOps, and it does not lock down a tenant. `openshift_tenant_lockdown` is the tenant check.

On provision it creates one Argo CD Application, `cluster-security-policy`, pointed at `cluster-security-policy` in this repo. That name is not `bootstrap-infra`. Content GitOps bootstrap keeps that name for its own Application, in another repository. `selfHeal` is true and `prune` is false. This role finishes when that Application is Healthy and Synced. It does not read the AdminNetworkPolicy or the `self-provisioner` binding. `ocp_workload_cluster_security_validation` does that, last.

`ocp4_workload_openshift_gitops` has to be earlier in the same workload list. The GitOps controller has to be allowed to create an AdminNetworkPolicy and to update ClusterRoleBinding `self-provisioner`. `ocp4_workload_openshift_gitops_setup_cluster_admin: true` does that.

## Role variables

| Variable | Default | Description |
|---|---|---|
| `ocp_workload_cluster_security_policy_repo_url` | `https://github.com/rhpds/security.git` | Git repo of the chart |
| `ocp_workload_cluster_security_policy_repo_revision` | `main` | Git revision Argo CD tracks |
| `ocp_workload_cluster_security_policy_repo_path` | `cluster-security-policy` | Path of the chart |
| `ocp_workload_cluster_security_policy_application_name` | `cluster-security-policy` | Application name |
| `ocp_workload_cluster_security_policy_namespace` | `openshift-gitops` | Namespace of the Application |
| `ocp_workload_cluster_security_policy_project` | `default` | Argo CD project. This role does not create an AppProject |
| `ocp_workload_cluster_security_policy_adminnetworkpolicy_name` | `tenant-egress` | AdminNetworkPolicy name |
| `ocp_workload_cluster_security_policy_adminnetworkpolicy_priority` | `50` | AdminNetworkPolicy priority |
| `ocp_workload_cluster_security_policy_self_provisioner` | `false` | `false` removes the self-provisioner groups. `true` puts them back |
| `ocp_workload_cluster_security_policy_extra_egress_cidrs` | `[]` | CIDRs outside the cluster, allowed before the deny |
| `ocp_workload_cluster_security_policy_allow_namespaces` | `openshift-image-registry` | Platform namespaces user workloads may connect to |
| `ocp_workload_cluster_security_policy_allowed_registries` | `quay.io`, `registry.redhat.io`, the internal registry, `docker.io`, `registry-1.docker.io` | Registries the nodes may pull. Anything else is blocked |
| `ocp_workload_cluster_security_policy_health_retries` | `60` | How many 10-second waits for Healthy and Synced |

## Catalog item

```yaml
workloads:
  - agnosticd.core_workloads.ocp4_workload_openshift_gitops
  - rhpds.security.ocp_workload_cluster_security_policy

ocp_workload_cluster_security_policy_self_provisioner: false
```
