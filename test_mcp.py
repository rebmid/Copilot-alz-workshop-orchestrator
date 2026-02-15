from ai.mcp_retriever import search_docs

results = search_docs("Azure Firewall hub spoke architecture")

print("Results:")
for r in results:
    print(r["title"])
    print(r["url"])
    print("-----")
