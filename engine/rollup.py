from collections import defaultdict

def rollup_by_section(results):

    sections = defaultdict(lambda: defaultdict(int))

    for r in results:
        sections[r["section"]][r["status"]] += 1

    return sections
