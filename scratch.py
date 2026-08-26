import os
import glob
import re

replacements = {
    r'text-mute-400': 'text-ink-500',
    r'text-mute-300': 'text-ink-600',
    r'text-mute-200': 'text-ink-700',
    r'text-mute-100': 'text-ink-900',
    r'border-ink-700': 'border-ink-200',
    r'border-ink-800': 'border-ink-200',
    r'bg-ink-950': 'bg-white',
    r'bg-ink-800': 'bg-ink-50',
    r'bg-ink-700': 'bg-ink-100',
    r'text-slick-400': 'text-orange-600',
    r'bg-ink-850/60': 'bg-white',
    r'ring-ink-950': 'ring-white',
    r'ring-ink-800': 'ring-ink-100',
}

files = glob.glob('/home/aarya_balan/My Space/Invictus-SIH2026/model/frontend/src/components/**/*.tsx', recursive=True)

for file in files:
    with open(file, 'r') as f:
        content = f.read()
    
    new_content = content
    for pattern, repl in replacements.items():
        new_content = re.sub(pattern, repl, new_content)
        
    if new_content != content:
        with open(file, 'w') as f:
            f.write(new_content)
        print(f"Updated {file}")

