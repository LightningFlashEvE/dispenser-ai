import os
import re

directory = r"e:\dispenser-ai\frontend\src"

replacements = {
    r"background:\s*var\(--wf-white\)": "background: var(--wf-bg-page)",
    r"background:\s*#ffffff": "background: var(--wf-bg-card)",
    r"background:\s*#fafafa": "background: var(--wf-bg-panel)",
    r"background:\s*#f5f5f5": "background: var(--wf-bg-panel)",
    r"background:\s*#f4f5f7": "background: var(--wf-bg-panel)",
    r"border:\s*1px solid var\(--wf-border\)": "border: 1px solid var(--wf-border-dark)",
    r"border-bottom:\s*1px solid var\(--wf-border\)": "border-bottom: 1px solid var(--wf-border-dark)",
    r"border-top:\s*1px solid var\(--wf-border\)": "border-top: 1px solid var(--wf-border-dark)",
    r"border-right:\s*1px solid var\(--wf-border\)": "border-right: 1px solid var(--wf-border-dark)",
    r"color:\s*var\(--wf-black\)": "color: var(--wf-text-main)",
    r"color:\s*var\(--wf-gray-mid\)": "color: var(--wf-text-muted)",
    r"color:\s*#080808": "color: var(--wf-text-main)",
    r"color:\s*#5a5a5a": "color: var(--wf-text-muted)",
    r"color:\s*var\(--wf-gray-300\)": "color: var(--wf-text-muted)",
}

for root, _, files in os.walk(directory):
    for file in files:
        if file.endswith((".vue", ".ts", ".css")):
            path = os.path.join(root, file)
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            
            new_content = content
            for pattern, repl in replacements.items():
                new_content = re.sub(pattern, repl, new_content)
                
            if new_content != content:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(new_content)
                print(f"Updated {path}")
