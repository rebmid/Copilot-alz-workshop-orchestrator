"""Fix escaped docstrings."""
with open("engine/relationship_integrity.py", "r", encoding="utf-8") as f:
    content = f.read()

content = content.replace('\\"\\"\\"', '"""')

with open("engine/relationship_integrity.py", "w", encoding="utf-8") as f:
    f.write(content)
print("Fixed")
