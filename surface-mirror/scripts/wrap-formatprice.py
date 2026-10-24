#!/usr/bin/env python3
"""Wrap all $$${var.toFixed(2)} with formatPrice(var) in index.html."""
import re
import sys
from pathlib import Path

p = Path(r"C:\Users\KING\Projects\krysys-shop\index.html")
s = p.read_text(encoding='utf-8')
before = s.count('formatPrice(')

# Pattern: ${var.toFixed(2)} → ${formatPrice(var)}
def wrap(m):
    inner = m.group(1)
    return '${formatPrice(' + inner + ')}'

# var form
s2 = re.sub(r'\$\$\{(\w+(?:\.\w+|\[[^\]]+\]|\|\|[^\]]+\])*)\.toFixed\(2\)\}', wrap, s)
# (expr) form
s3 = re.sub(r'\$\$\{(\([^}]+\))\.toFixed\(2\)\}', wrap, s2)

after = s3.count('formatPrice(')
print(f'Wraps added: {after - before}')
p.write_text(s3, encoding='utf-8')