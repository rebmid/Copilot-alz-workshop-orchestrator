from collectors.resource_graph import get_subscriptions, query_resource_graph


def collect_policy_assignments():
    subscriptions = get_subscriptions()

    query = """
    PolicyResources
    | where type =~ 'microsoft.authorization/policyassignments'
    | project name, id, properties.displayName, properties.policyDefinitionId, properties.scope
    """
    data = query_resource_graph(query, subscriptions)

    return {"assignments": data}
