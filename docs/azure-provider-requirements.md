# Required Azure Resource Providers

The tool queries Azure Resource Graph and ARM APIs using **read-only** calls. The following resource providers must be registered on the target subscriptions for all signals to return data. Most are registered by default on any subscription that has used the service — but if a signal returns empty, missing provider registration is the most common cause.

| Resource Provider | Signal(s) | Registered by Default? |
|---|---|---|
| `Microsoft.ResourceGraph` | All Resource Graph queries | ✅ Yes |
| `Microsoft.Network` | Firewalls, VNets, Public IPs, NSGs, Route Tables, Private Endpoints, DDoS | ✅ Yes |
| `Microsoft.Storage` | Storage Account Posture | ✅ Yes |
| `Microsoft.KeyVault` | Key Vault Posture | ✅ Yes |
| `Microsoft.Sql` | SQL Server Posture | Only if SQL is used |
| `Microsoft.Web` | App Service Posture | Only if App Service is used |
| `Microsoft.ContainerRegistry` | Container Registry Posture | Only if ACR is used |
| `Microsoft.ContainerService` | AKS Cluster Posture | Only if AKS is used |
| `Microsoft.RecoveryServices` | VM Backup Coverage | Only if Backup is configured |
| `Microsoft.Compute` | VM inventory (for backup coverage) | ✅ Yes |
| `Microsoft.Security` | Defender plans, Secure Score | ✅ Yes |
| `Microsoft.Authorization` | RBAC hygiene, Resource Locks, Policy assignments | ✅ Yes (built-in) |
| `Microsoft.PolicyInsights` | Policy compliance summary | ✅ Yes |
| `Microsoft.Management` | Management Group hierarchy | ✅ Yes |
| `Microsoft.Insights` | Diagnostics coverage | ✅ Yes |

## Checking Registration Status

```bash
az provider show -n Microsoft.RecoveryServices --query "registrationState" -o tsv
```

## Registering a Missing Provider

Requires Contributor or Owner:

```bash
az provider register -n Microsoft.RecoveryServices
```

> **Note:** If a resource type doesn't exist in the subscription (e.g., no AKS clusters), the evaluator returns **NotApplicable** — not an error. Missing provider registration only matters when you *have* those resources but the signal returns empty.
