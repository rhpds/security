# ocp_workload_cluster_security_validation

Last workload on a cluster catalog item. It does not install anything and it does not repair anything. `ocp_workload_cluster_security_policy` trusts Argo CD once the Application is Healthy and Synced. This role runs after the other workloads and reads the objects. If they are missing or no longer match the chart, the provision fails and the cluster is not released.

It checks:

- AdminNetworkPolicy `tenant-egress` matches the chart
- ClusterRoleBinding `self-provisioner` matches `ocp_workload_cluster_security_policy_self_provisioner`

On destroy it does nothing to those objects.

`ocp_workload_cluster_security_policy` has to be earlier in the workload list. This role runs after content bootstrap and Showroom.

## Catalog item

```yaml
workloads:
  - agnosticd.core_workloads.ocp4_workload_openshift_gitops
  - rhpds.security.ocp_workload_cluster_security_policy
  - agnosticd.core_workloads.ocp4_workload_gitops_bootstrap
  - rhpds.security.ocp_workload_cluster_security_validation
```
