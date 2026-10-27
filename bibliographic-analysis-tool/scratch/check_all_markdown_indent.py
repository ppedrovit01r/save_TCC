import os

workspace = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
py_files = []
for root, dirs, files in os.walk(workspace):
    if any(p in root for p in ['.git', '__pycache__', 'venv', '.gemini', 'scratch']):
        continue
    for f in files:
        if f.endswith('.py'):
            py_files.append(os.path.join(root, f))

found = []
for p in py_files:
    rel = os.path.relpath(p, workspace)
    with open(p, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    for idx, line in enumerate(lines):
        if 'st.markdown(' in line and ('"""' in line or "'''" in line):
            window = "".join(lines[idx:min(idx+35, len(lines))])
            if 'unsafe_allow_html=True' in window and '<div' in window:
                # Check if there are indented html lines inside
                for sub_i in range(idx+1, min(idx+35, len(lines))):
                    sub_line = lines[sub_i]
                    if '"""' in sub_line or "'''" in sub_line:
                        break
                    # If line starts with 4+ spaces and contains HTML tags
                    if sub_line.startswith('    ') and ('<' in sub_line and '>' in sub_line):
                        found.append((rel, idx+1, line.strip()))
                        break

print(f"Total potential indented HTML blocks found: {len(found)}")
for f in found:
    print(f"{f[0]}:{f[1]} -> {f[2]}")
