import re

with open('features/prisma_assistant.py', 'r', encoding='utf-8') as f:
    content = f.read()

matches = re.finditer(r'st\.markdown\s*\(\s*(?:f|r|rf|fr)?\"\"\"(.*?)\"\"\"', content, re.DOTALL)
for m in matches:
    block = m.group(1)
    lines = [l for l in block.splitlines() if l.strip()]
    indented_html = [l for l in lines if (l.startswith('    ') or l.startswith('\t')) and ('<' in l or '>' in l)]
    if indented_html:
        start_line = content[:m.start()].count('\n') + 1
        print(f"Line {start_line}: {len(indented_html)} indented HTML lines. First: {indented_html[0].strip()[:60]}")
