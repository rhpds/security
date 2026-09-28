# ocp_workload_cluster_security_validation

Last workload on a cluster catalog item. It does not install anything and it does not repair anything.

`ocp_workload_cluster_security_policy` writes the desired policy into Application `cluster-security-policy` and trusts Argo CD once that Application is Healthy and Synced. This role runs after the other workloads. It reads the Application helm values and compares the live objects to those values. The helm values are the source of truth. This role does not keep its own copy of the registry list, the namespace allows, or the priorities.

It checks:

- Application `cluster-security-policy` is Healthy and Synced
- AdminNetworkPolicy named by the Application matches those helm values
- `image.config.openshift.io/cluster` `allowedRegistries` matches the Application, and `blockedRegistries` is empty
- ClusterRoleBinding `self-provisioner` matches `selfProvisioner.enabled` from the Application

The report is written with `agnosticd.core.agnosticd_user_info` as `msg` and as `cluster_security_report` / `cluster_security_report_status` in `data`. The catalog info page shows those keys. Any failed check fails the provision, and the cluster is not released.

On destroy it does nothing to those objects.

## Catalog item

```yaml
workloads:
  - agnosticd.core_workloads.ocp4_workload_openshift_gitops
  - rhpds.security.ocp_workload_cluster_security_policy
  - agnosticd.core_workloads.ocp4_workload_gitops_bootstrap
  - rhpds.security.ocp_workload_cluster_security_validation
```

A catalog item changes the policy through `ocp_workload_cluster_security_policy_*` variables. Those are rendered into the Application. This role follows the Application.
