"""扫描 .vue 文件的 <template> 段，找出所有含英文的界面文案"""
import re
from pathlib import Path

ROOT = Path('D:/桌面/etf/quant-fletch/web/app')
FILES = sorted(list(ROOT.rglob('*.vue')) + list(ROOT.rglob('*.ts')))

TEXT_RE = re.compile(r'>([^<>{}\n]*[A-Za-z]{2,}[^<>{}\n]*)<')
ATTR_RE = re.compile(r'(title|placeholder|label|aria-label|alt)="([^"]*[A-Za-z]{2,}[^"]*)"')
# 跳过这些明显是代码/样式的值
SKIP = ('http', 'className', 'i-ph-', 'sr-only')

total = 0
for f in FILES:
    src = f.read_text(encoding='utf-8')
    hits = []
    if f.suffix == '.vue':
        # 注意用贪婪匹配: <template> 可嵌套 (如 <template #hint>),
        # 非贪婪会在第一个 </template> 提前截断, 漏掉后半部分文案
        m = re.search(r'<template>(.*)</template>', src, re.S)
        if not m:
            continue
        body = m.group(1)
        offset = src[:m.start(1)].count('\n')
        for mm in TEXT_RE.finditer(body):
            val = mm.group(1).strip()
            if val and not any(s in val for s in SKIP):
                line = offset + body[:mm.start()].count('\n') + 1
                hits.append((line, 'text', val))
        for mm in ATTR_RE.finditer(body):
            line = offset + body[:mm.start()].count('\n') + 1
            hits.append((line, mm.group(1), mm.group(2)))
    else:
        for mm in ATTR_RE.finditer(src):
            line = src[:mm.start()].count('\n') + 1
            hits.append((line, mm.group(1), mm.group(2)))

    if hits:
        print(f'\n--- {f.relative_to(ROOT)} ---')
        for line, kind, val in sorted(set(hits)):
            print(f'  {line:>4} [{kind}] {val[:70]}')
            total += 1

print(f'\n合计 {total} 处')
