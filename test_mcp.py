from ai.mcp_retriever import search_learn

results = search_learn("Azure Firewall hub spoke architecture")

print("Results:")
for r in results:
    print(r["title"])
    print(r["url"])
    print("-----")
