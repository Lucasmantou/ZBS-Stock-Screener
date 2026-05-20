#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
个股深度研究报告 HTML渲染器 v8.0
专业级设计：左侧目录 + 右侧内容 + 精细化排版
"""

import json
import os
import re
from datetime import datetime

def load_data(json_file):
    with open(json_file, 'r', encoding='utf-8') as f:
        return json.load(f)

def load_markdown(md_file):
    with open(md_file, 'r', encoding='utf-8') as f:
        return f.read()

def extract_basic_info(data):
    """提取基本信息"""
    basic_dict = {item['item']: item['value'] for item in data['blocks'].get('basic_info', [])}
    spot = data['blocks']['spot'][0] if data['blocks'].get('spot') else {}
    fin = data['blocks'].get('fin_indicator_ths', [])

    # 从 spot 数据中提取名称和代码
    spot_name = spot.get('名称', '--')
    spot_code = str(spot.get('代码', '000000')).replace('sz', '').replace('sh', '')

    # 从 spot 数据计算市盈率：最新价 / 最新年报每股收益（TTM用年报EPS）
    pe = '--'
    if fin:
        # 优先用最近一年的年报EPS（12-31），避免单季EPS导致PE虚高
        annual_eps = None
        for item in reversed(fin):
            if item.get('报告期', '').endswith('12-31'):
                annual_eps = item.get('基本每股收益')
                break
        # fallback 到最新一条
        if not annual_eps:
            annual_eps = fin[-1].get('基本每股收益')
        price = spot.get('最新价')
        if annual_eps and price:
            try:
                pe_val = round(float(price) / float(annual_eps), 2)
                pe = f"{pe_val:.2f}"
            except (ValueError, ZeroDivisionError):
                pe = '--'

    # 从 spot + share_structure 计算总市值
    market_cap = '--'
    price = spot.get('最新价')
    total_shares = data['blocks'].get('share_structure', [{}])[0].get('总股本') if data['blocks'].get('share_structure') else None
    if price and total_shares:
        try:
            mc = float(price) * int(total_shares)
            if mc >= 1e8:
                market_cap = f"{mc/1e8:.2f}亿"
            else:
                market_cap = f"{mc/1e4:.0f}万"
        except (ValueError, TypeError):
            pass

    # 尝试从 zygc 提取主营业务
    business = basic_dict.get('主营业务', '未知')
    if business == '未知':
        zygc = data['blocks'].get('zygc', [])
        if zygc:
            # 按最新一期、按产品分类，取前3项合并
            latest_date = zygc[0]['报告日期'][:7]
            products = [z['主营构成'] for z in zygc if z['报告日期'].startswith(latest_date) and z['分类类型'] == '按产品分类']
            if products:
                business = '、'.join(products[:3])

    # 尝试从 zygc 提取行业（第一行分类类型为None的是行业汇总）
    industry = basic_dict.get('所属行业', '未知')
    if industry == '未知':
        zygc = data['blocks'].get('zygc', [])
        if zygc:
            industry_summary = [z for z in zygc if z.get('分类类型') is None]
            if industry_summary:
                industry = industry_summary[0].get('主营构成', '未知')

    return {
        'name': data.get('name') or spot_name or '未知',
        'code': data.get('code') or spot_code or '000000',
        'industry': industry,
        'business': business,
        'price': spot.get('最新价', '--'),
        'change': spot.get('涨跌幅', '--'),
        'pe': pe,
        'market_cap': market_cap
    }

def extract_business_composition(data):
    """提取主营业务构成"""
    zygc = data['blocks'].get('zygc', [])
    if not zygc:
        return []
    latest_date = zygc[0]['报告日期'][:7]
    product_data = []
    for item in zygc:
        if item['报告日期'].startswith(latest_date) and item['分类类型'] == '按产品分类':
            product_data.append({
                'name': item['主营构成'],
                'value': round(item['主营收入'] / 100000000, 2),
                'ratio': round(item['收入比例'] * 100, 2)
            })
    return product_data[:6]

def extract_news(data):
    """提取近期新闻"""
    news = data['blocks'].get('news', [])
    return [n.get('新闻标题', 'N/A') for n in news[:5]]

def extract_target_price(md_content):
    """提取买入价和卖出价"""
    # 尝试提取买入价区间（支持表格格式和行内格式）
    buy_match = re.search(r'买入价[区间：:]*\s*(\d+\.?\d*)\s*[-~—至]\s*(\d+\.?\d*)', md_content)
    if not buy_match:
        buy_match = re.search(r'建议买入[价格：:]*\s*(\d+\.?\d*)\s*[-~—至]\s*(\d+\.?\d*)', md_content)
    if not buy_match:
        # 表格格式：在"买入价区间"附近找含"元"的价格对
        buy_area = re.search(r'买入价区间.*?(?=\n##|\Z)', md_content, re.DOTALL)
        if buy_area:
            prices = re.findall(r'(\d+\.?\d*)\s*[-~—至]\s*(\d+\.?\d*)\s*元', buy_area.group())
            if prices:
                lows = [float(p[0]) for p in prices]
                highs = [float(p[1]) for p in prices]
                buy_match = type('M', (), {'group': lambda self, n: str(min(lows)) if n == 1 else str(max(highs))})()
    # 尝试提取止损价
    stop_match = re.search(r'止损[价位：:]*\s*(\d+\.?\d*)', md_content)
    if not stop_match:
        stop_match = re.search(r'跌破[（(]?(\d+\.?\d*)元', md_content)
    # 尝试提取卖出目标价
    sell_match = re.search(r'目标[价一1]?[：:]*\s*(\d+\.?\d*)', md_content)
    if not sell_match:
        sell_match = re.search(r'卖出[价格：:]*\s*(\d+\.?\d*)', md_content)

    # 从三档目标价中提取
    short_target = re.search(r'短期.*?(\d+)-(\d+)元', md_content)
    mid_target = re.search(r'中期.*?(\d+)-(\d+)元', md_content)
    long_target = re.search(r'长期.*?(\d+)-(\d+)元', md_content)

    # 从盈亏比部分提取
    up_price = re.search(r'向上.*?(\d+\.?\d*)元', md_content)
    down_price = re.search(r'向下.*?(\d+\.?\d*)元', md_content)

    stop_loss = stop_match.group(1) if stop_match else "--"
    sell_price = sell_match.group(1) if sell_match else (mid_target.group(1) if mid_target else "--")
    sell_high = mid_target.group(2) if mid_target else "--"

    # 计算买入区间：优先用明确的买入价，否则用当前价附近
    if buy_match:
        buy_low = buy_match.group(1)
        buy_high = buy_match.group(2)
    elif up_price and stop_loss != "--":
        # 从盈亏比反推：向上目标价 - 一定空间 = 买入区间上界
        try:
            target = float(up_price.group(1))
            stop = float(stop_loss)
            buy_high_val = round(target * 0.9, 2)  # 目标价9折
            buy_low_val = round(stop * 1.05, 2)     # 止损价上浮5%
            buy_low = str(buy_low_val)
            buy_high = str(buy_high_val)
        except ValueError:
            buy_low = "--"
            buy_high = "--"
    else:
        buy_low = "--"
        buy_high = "--"

    return {
        'buy_low': buy_low,
        'buy_high': buy_high,
        'stop_loss': stop_loss,
        'sell_price': sell_price,
        'sell_high': sell_high,
    }

def clean_markdown(text):
    """清理Markdown标记"""
    # 移除###标记
    text = re.sub(r'###\s+', '', text)
    # 移除**加粗标记但保留内容
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    # 移除代码块标记
    text = re.sub(r'```\n?', '', text)
    return text

def format_table(table_text):
    """格式化表格"""
    lines = [l.strip() for l in table_text.split('\n') if l.strip() and '|' in l]
    if len(lines) < 2:
        return table_text

    html = '<table class="data-table">'
    for i, line in enumerate(lines):
        if '---' in line:
            continue
        cells = [c.strip() for c in line.split('|')[1:-1]]
        if i == 0:
            html += '<thead><tr>' + ''.join([f'<th>{c}</th>' for c in cells]) + '</tr></thead><tbody>'
        else:
            html += '<tr>' + ''.join([f'<td>{c}</td>' for c in cells]) + '</tr>'
    html += '</tbody></table>'
    return html

def parse_step_sections(md_content):
    """解析Part I-V及基本信息/财务摘要，精细化处理每个部分"""
    sections = []

    # 匹配所有 ## 级别的标题（Step/Part/基本信息/财务摘要）
    pattern = r'## ([^\n]+)\n(.*?)(?=\n## [^\n]+|$)'
    matches = re.findall(pattern, md_content, re.DOTALL)

    for title, content in matches:
        # 跳过非分析章节（如一级标题、分隔线）
        if title.startswith('#') or title.strip() == '---':
            continue
        # 清理标题
        clean_title = re.sub(r'^(Step \d+:\s*|Part [IVXLC]+:\s*)', '', title).strip()

        # 处理内容
        content = clean_markdown(content)

        # 处理表格
        if '|' in content:
            table_blocks = re.findall(r'(\|[^\n]+\|(?:\n\|[^\n]+\|)+)', content)
            for table in table_blocks:
                formatted = format_table(table)
                content = content.replace(table, formatted)

        # 处理列表
        content = re.sub(r'\n- (.+)', r'<li>\1</li>', content)
        if '<li>' in content:
            content = '<ul class="styled-list">' + content + '</ul>'

        # 处理段落
        paragraphs = content.split('\n\n')
        content = ''.join([f'<p>{p}</p>' for p in paragraphs if p.strip()])

        # Generate ID from title
        step_id = re.sub(r'[^a-zA-Z0-9\u4e00-\u9fff]', '', title.split(':')[0].replace('Step ', '').replace('Part ', 'part-').lower())

        sections.append({
            'id': step_id,
            'title': clean_title,
            'content': content
        })

    return sections

def generate_industry_chain_svg(name='公司', upstream='原材料', midstream='加工制造', downstream='终端应用'):
    """生成产业链SVG图"""
    return f'''
<svg viewBox="0 0 800 300" xmlns="http://www.w3.org/2000/svg">
  <!-- 上游 -->
  <rect x="50" y="120" width="150" height="60" fill="#e8f5e9" stroke="#4caf50" stroke-width="2" rx="8"/>
  <text x="125" y="145" text-anchor="middle" font-size="14" font-weight="600">上游</text>
  <text x="125" y="165" text-anchor="middle" font-size="12">{upstream}</text>

  <!-- 箭头1 -->
  <path d="M 200 150 L 280 150" stroke="#666" stroke-width="2" marker-end="url(#arrowhead)"/>

  <!-- 中游 -->
  <rect x="280" y="100" width="180" height="100" fill="#fff3e0" stroke="#ff9800" stroke-width="3" rx="8"/>
  <text x="370" y="130" text-anchor="middle" font-size="16" font-weight="700" fill="#e65100">中游（{name}）</text>
  <text x="370" y="155" text-anchor="middle" font-size="12">{midstream}</text>

  <!-- 箭头2 -->
  <path d="M 460 150 L 540 150" stroke="#666" stroke-width="2" marker-end="url(#arrowhead)"/>

  <!-- 下游 -->
  <rect x="540" y="120" width="150" height="60" fill="#e3f2fd" stroke="#2196f3" stroke-width="2" rx="8"/>
  <text x="615" y="145" text-anchor="middle" font-size="14" font-weight="600">下游</text>
  <text x="615" y="165" text-anchor="middle" font-size="12">{downstream}</text>

  <!-- 箭头定义 -->
  <defs>
    <marker id="arrowhead" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto">
      <polygon points="0 0, 10 3, 0 6" fill="#666"/>
    </marker>
  </defs>
</svg>
'''

def generate_html(stock_code, md_file, json_file):
    data = load_data(json_file)
    md_content = load_markdown(md_file)

    info = extract_basic_info(data)
    business = extract_business_composition(data)
    news_list = extract_news(data)
    target_info = extract_target_price(md_content)
    sections = parse_step_sections(md_content)

    # K线数据 — 过滤掉无成交的无效日（volume=0 或 open=0）
    kline_raw = data['blocks'].get('kline_daily', [])
    kline_data = [d for d in kline_raw
                  if d.get('volume', 0) and d.get('open', 0)
                  and d['volume'] > 0 and d['open'] > 0][-60:]
    dates = [d['date'][:10] for d in kline_data]
    ohlc = [[d['open'], d['close'], d['low'], d['high']] for d in kline_data]
    volumes = [d.get('volume', 0) for d in kline_data]

    # 计算MA均线（用JSON序列化确保None→null）
    closes = [d['close'] for d in kline_data]
    ma5 = []
    ma20 = []
    ma60 = []
    for i in range(len(closes)):
        if i >= 4:
            ma5.append(round(sum(closes[i-4:i+1])/5, 2))
        else:
            ma5.append(None)
        if i >= 19:
            ma20.append(round(sum(closes[i-19:i+1])/20, 2))
        else:
            ma20.append(None)
        if i >= 59:
            ma60.append(round(sum(closes[i-59:i+1])/60, 2))
        else:
            ma60.append(None)
    # 转JSON确保None变成null
    ma5_str = json.dumps(ma5)
    ma20_str = json.dumps(ma20)
    ma60_str = json.dumps(ma60)

    # 饼图数据
    pie_data = str([{'name': b['name'], 'value': b['value']} for b in business])

    # 新闻HTML
    news_html = ''.join([f'<div class="news-item"><span class="news-dot">•</span>{n}</div>' for n in news_list])

    # 目录HTML
    toc_html = ''.join([f'<a href="#{sec["id"]}" class="toc-item">{sec["title"]}</a>' for sec in sections])

    # 内容HTML — 带编号 + 巨型标题
    sections_html = ""
    roman = ['I','II','III','IV','V','VI','VII','VIII','IX','X']
    part_idx = 0  # 仅 Step/Part 类章节计数
    for sec in sections:
        # 特殊处理产业链部分
        content = sec['content']
        if ('step2' in sec['id'] or 'part-ii' in sec['id']) and '上游' in content:
            content = generate_industry_chain_svg(
                name=info['name'],
                upstream='铝材、钢材等',
                midstream='精密金属加工',
                downstream='汽车、电子、机械零部件'
            ) + content

        is_step_or_part = sec['id'].startswith('step') or sec['id'].startswith('part')
        if is_step_or_part:
            num_label = roman[part_idx] if part_idx < len(roman) else str(part_idx+1)
            part_idx += 1
            num_html = f'<div class="section-num">PART {num_label}</div>'
        else:
            num_html = ''

        sections_html += f'''
<section id="{sec['id']}" class="content-section">
    {num_html}
    <h2 class="section-title">{sec['title']}</h2>
    <div class="section-rule"></div>
    <div class="section-content">{content}</div>
</section>
'''

    # 动态生成导航项
    nav_items = '<a href="#overview" class="nav-item active">总览</a>\n'
    nav_items += '<a href="#charts" class="nav-item">图表</a>\n'
    for sec in sections:
        nav_items += f'<a href="#{sec["id"]}" class="nav-item">{sec["title"]}</a>\n'
    # 添加术语表导航
    nav_items += '<a href="#glossary" class="nav-item">术语表</a>\n'

    # 涨跌颜色
    change_class = 'up' if float(info['change']) > 0 else 'down'
    change_prefix = '+' if float(info['change']) > 0 else ''

    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ZBS · {info['name']}（{info['code']}）深度研究</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.min.js"></script>
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,500;0,9..40,700;0,9..40,900;1,9..40,400&family=JetBrains+Mono:wght@400;600;700&display=swap');

*{{margin:0;padding:0;box-sizing:border-box}}
:root{{
  --bg:#090c14;--surface:#111520;--surface-2:#181d2a;--surface-3:#1e2436;
  --border:#252b3a;--border-2:#2e3548;
  --text:#d8dce6;--text-2:#9aa0b4;--text-3:#5a6278;
  --accent:#3b82f6;--accent-dim:rgba(59,130,246,0.08);--accent-mid:rgba(59,130,246,0.18);
  --accent-glow:rgba(59,130,246,0.3);
  --red:#f43f5e;--red-dim:rgba(244,63,94,0.12);
  --green:#10b981;--green-dim:rgba(16,185,129,0.12);
  --amber:#f59e0b;
  --sidebar-w:260px;
  --font:'DM Sans','Inter','Noto Sans SC','PingFang SC','Microsoft YaHei',sans-serif;
  --mono:'JetBrains Mono','IBM Plex Mono','SF Mono','Consolas',monospace;
  --ease:0.2s cubic-bezier(0.4,0,0.2,1);
}}
body.light-mode{{
  --bg:#f0f2f5;--surface:#fff;--surface-2:#f7f8fa;--surface-3:#eceef2;
  --border:#dce0e8;--border-2:#c8cdd8;
  --text:#1a1f2e;--text-2:#5a6278;--text-3:#8b92a8;
  --accent:#2563eb;--accent-dim:rgba(37,99,235,0.06);--accent-mid:rgba(37,99,235,0.14);
  --accent-glow:rgba(37,99,235,0.2);
  --red:#e11d48;--red-dim:rgba(225,29,72,0.08);
  --green:#059669;--green-dim:rgba(5,150,105,0.08);
}}
html{{scroll-behavior:smooth}}
body{{font-family:var(--font);background:var(--bg);color:var(--text);font-size:15px;line-height:1.7;overflow-x:hidden}}

/* ═══════════════════════════════════════════
   LEFT SIDEBAR
   ═══════════════════════════════════════════ */
.sidebar{{
  position:fixed;top:0;left:0;width:var(--sidebar-w);height:100vh;
  background:var(--surface);border-right:1px solid var(--border);
  display:flex;flex-direction:column;z-index:100;overflow-y:auto;
  transition:transform 0.3s var(--ease);
}}
.sidebar-header{{
  padding:24px 20px 16px;border-bottom:1px solid var(--border);
}}
.logo{{
  font-family:var(--mono);font-weight:900;font-size:22px;color:var(--accent);
  letter-spacing:4px;text-transform:uppercase;margin-bottom:16px;
}}
.stock-badge{{
  background:var(--surface-2);border:1px solid var(--border);padding:14px 16px;
}}
.stock-badge .sb-name{{font-size:18px;font-weight:700;color:var(--text);margin-bottom:2px}}
.stock-badge .sb-code{{font-size:12px;color:var(--text-3);font-family:var(--mono);margin-bottom:10px}}
.stock-badge .sb-price{{
  font-size:28px;font-weight:900;font-family:var(--mono);
  font-variant-numeric:tabular-nums;color:var(--text);line-height:1;
}}
.stock-badge .sb-change{{
  display:inline-block;font-size:13px;font-weight:700;font-family:var(--mono);
  padding:2px 8px;margin-top:6px;
}}
.stock-badge .sb-change.up{{color:var(--red);background:var(--red-dim)}}
.stock-badge .sb-change.down{{color:var(--green);background:var(--green-dim)}}

.sidebar-nav{{flex:1;padding:12px 0;overflow-y:auto}}
.nav-item{{
  display:block;padding:10px 20px;font-size:13px;font-weight:500;
  color:var(--text-2);text-decoration:none;border-left:3px solid transparent;
  transition:var(--ease);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
}}
.nav-item:hover{{color:var(--text);background:var(--accent-dim);border-left-color:var(--accent-mid)}}
.nav-item.active{{color:var(--accent);background:var(--accent-dim);border-left-color:var(--accent);font-weight:700}}

.sidebar-footer{{
  padding:12px 20px;border-top:1px solid var(--border);display:flex;gap:8px;
}}
.theme-btn{{
  flex:1;padding:8px;background:var(--surface-2);border:1px solid var(--border);
  color:var(--text-2);font-size:11px;font-family:var(--mono);cursor:pointer;
  transition:var(--ease);font-weight:600;
}}
.theme-btn:hover{{border-color:var(--accent);color:var(--accent)}}
.gen-time{{font-size:10px;color:var(--text-3);font-family:var(--mono);padding:0 20px 12px;text-align:center}}

/* ═══════════════════════════════════════════
   MAIN CONTENT
   ═══════════════════════════════════════════ */
.main{{margin-left:var(--sidebar-w);min-height:100vh;padding:0}}

/* ── Hero overview ── */
.hero{{
  padding:48px 48px 40px;border-bottom:1px solid var(--border);
  background:linear-gradient(180deg,var(--surface) 0%,var(--bg) 100%);
}}
.hero-label{{
  font-size:11px;font-weight:700;color:var(--accent);letter-spacing:3px;
  text-transform:uppercase;font-family:var(--mono);margin-bottom:12px;
}}
.hero-title{{
  font-size:clamp(36px,5vw,56px);font-weight:900;line-height:1.05;
  color:var(--text);margin-bottom:8px;letter-spacing:-1px;
}}
.hero-sub{{font-size:16px;color:var(--text-2);margin-bottom:32px}}

/* KPI strip */
.kpi-strip{{
  display:grid;grid-template-columns:repeat(4,1fr);gap:1px;
  background:var(--border);border:1px solid var(--border);
}}
.kpi-card{{
  background:var(--surface);padding:20px 24px;text-align:center;
}}
.kpi-card .kv{{
  font-size:26px;font-weight:900;font-family:var(--mono);
  font-variant-numeric:tabular-nums;color:var(--text);line-height:1.1;
}}
.kpi-card .kv.accent{{color:var(--accent)}}
.kpi-card .kv.red{{color:var(--red)}}
.kpi-card .kv.green{{color:var(--green)}}
.kpi-card .kl{{
  font-size:11px;color:var(--text-3);margin-top:6px;letter-spacing:1px;
  text-transform:uppercase;font-weight:600;font-family:var(--mono);
}}
.kpi-card .ks{{font-size:11px;color:var(--text-3);margin-top:3px}}

/* ── Content sections ── */
.content-wrap{{padding:32px 48px 60px}}

/* Section — each Part gets a GIANT title */
.content-section{{margin-bottom:48px}}
.section-num{{
  font-size:11px;font-weight:800;color:var(--accent);font-family:var(--mono);
  letter-spacing:2px;text-transform:uppercase;margin-bottom:8px;
}}
.section-title{{
  font-size:clamp(28px,3.5vw,42px);font-weight:900;color:var(--text);
  line-height:1.15;margin-bottom:8px;letter-spacing:-0.5px;
}}
.section-rule{{
  width:60px;height:3px;background:var(--accent);margin-bottom:28px;
}}
.section-content{{font-size:16px;color:var(--text-2);line-height:1.85}}
.section-content p{{margin:14px 0}}
.section-content strong{{color:var(--text);font-weight:700}}

/* ── Profile row ── */
.profile-row{{display:grid;grid-template-columns:1.4fr 1fr;gap:20px;margin-bottom:32px}}
.card{{
  background:var(--surface);border:1px solid var(--border);padding:24px;
}}
.card-title{{
  font-size:16px;font-weight:700;color:var(--text);margin-bottom:16px;
  padding-bottom:12px;border-bottom:1px solid var(--border);
  display:flex;align-items:center;gap:8px;
}}
.card-title .ico{{color:var(--accent);font-size:18px}}
.profile-content{{font-size:15px;line-height:1.8;color:var(--text-2)}}
.profile-content strong{{color:var(--text)}}
.profile-tags{{display:flex;flex-wrap:wrap;gap:8px;margin:14px 0}}
.tag{{
  padding:4px 14px;font-size:12px;font-weight:600;font-family:var(--mono);
  background:var(--accent-dim);color:var(--accent);border:1px solid var(--accent-mid);
  letter-spacing:0.3px;
}}
.news-list{{max-height:280px;overflow-y:auto}}
.news-item{{
  padding:10px 0;font-size:14px;color:var(--text-2);
  border-bottom:1px solid var(--border);display:flex;gap:8px;
}}
.news-dot{{color:var(--accent);font-weight:700}}

/* ── Charts ── */
.chart-row{{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:20px}}
#business-pie,#kline-small{{width:100%;height:380px}}
#kline-full{{width:100%;height:520px}}
.kline-info{{
  display:grid;grid-template-columns:repeat(3,1fr);gap:1px;
  background:var(--border);border:1px solid var(--border);margin-top:16px;
}}
.kline-info .ki{{background:var(--surface);padding:16px;text-align:center}}
.kline-info .kil{{font-size:12px;color:var(--text-3);margin-bottom:4px;font-family:var(--mono);letter-spacing:0.5px;text-transform:uppercase}}
.kline-info .kiv{{font-size:22px;font-weight:800;color:var(--accent);font-family:var(--mono)}}

/* ── Tables ── */
.data-table{{width:100%;border-collapse:collapse;margin:16px 0;font-size:15px}}
.data-table thead{{background:var(--surface-2)}}
.data-table th{{
  padding:12px 14px;text-align:left;font-weight:700;font-size:12px;
  border-bottom:2px solid var(--border);color:var(--text-3);
  letter-spacing:0.8px;text-transform:uppercase;font-family:var(--mono);
}}
.data-table td{{padding:10px 14px;border-bottom:1px solid var(--border);color:var(--text-2)}}
.data-table tr:hover{{background:var(--accent-dim)}}

/* ── Lists ── */
.styled-list{{margin:14px 0 14px 20px;list-style:none}}
.styled-list li{{margin:8px 0;padding-left:14px;border-left:3px solid var(--accent);color:var(--text-2);font-size:15px}}

/* ── SVG ── */
svg{{max-width:100%;height:auto;margin:20px 0}}

/* ── Footer ── */
footer{{
  text-align:center;padding:28px;color:var(--text-3);font-size:12px;
  border-top:1px solid var(--border);font-family:var(--mono);
}}

/* ═══════════════════════════════════════════
   MOBILE HAMBURGER
   ═══════════════════════════════════════════ */
.ham{{
  display:none;position:fixed;top:16px;left:16px;z-index:200;
  width:40px;height:40px;background:var(--surface);border:1px solid var(--border);
  cursor:pointer;flex-direction:column;align-items:center;justify-content:center;gap:5px;
}}
.ham span{{display:block;width:18px;height:2px;background:var(--text-2);transition:var(--ease)}}
.ham.on span:nth-child(1){{transform:rotate(45deg) translate(3px,3px)}}
.ham.on span:nth-child(2){{opacity:0}}
.ham.on span:nth-child(3){{transform:rotate(-45deg) translate(3px,-3px)}}
.mob-overlay{{
  display:none;position:fixed;inset:0;z-index:150;
  background:rgba(9,12,20,0.7);backdrop-filter:blur(8px);
}}
.mob-overlay.on{{display:block}}

/* ═══════════════════════════════════════════
   RESPONSIVE
   ═══════════════════════════════════════════ */
@media(max-width:1024px){{
  .sidebar{{transform:translateX(-100%)}}
  .sidebar.open{{transform:translateX(0)}}
  .ham{{display:flex}}
  .main{{margin-left:0}}
  .hero,.content-wrap{{padding-left:20px;padding-right:20px}}
}}
@media(max-width:768px){{
  .kpi-strip{{grid-template-columns:repeat(2,1fr)}}
  .chart-row,.profile-row{{grid-template-columns:1fr}}
  .hero-title{{font-size:32px}}
  .section-title{{font-size:28px}}
}}
@media(max-width:480px){{
  .kpi-strip{{grid-template-columns:1fr}}
  .hero{{padding:32px 16px 28px}}
  .content-wrap{{padding:24px 16px 40px}}
}}

/* ═══════════════════════════════════════════
   PRINT
   ═══════════════════════════════════════════ */
@media print{{
  .sidebar,.ham,.mob-overlay,.theme-btn{{display:none!important}}
  .main{{margin-left:0}}
  body{{background:#fff;color:#000}}
  .hero,.card,.content-section{{border:1px solid #ddd;background:#fff}}
  .section-title{{color:#000}}
  .data-table th{{background:#f5f5f5;color:#000}}
}}
</style>
</head>
<body>

<!-- Hamburger (mobile) -->
<button class="ham" onclick="document.querySelector('.sidebar').classList.toggle('open');this.classList.toggle('on');document.querySelector('.mob-overlay').classList.toggle('on')">
  <span></span><span></span><span></span>
</button>
<div class="mob-overlay" onclick="document.querySelector('.sidebar').classList.remove('open');document.querySelector('.ham').classList.remove('on');this.classList.remove('on')"></div>

<!-- LEFT SIDEBAR -->
<aside class="sidebar">
  <div class="sidebar-header">
    <div class="logo">ZBS</div>
    <div class="stock-badge">
      <div class="sb-name">{info['name']}</div>
      <div class="sb-code">{info['code']} · {info['industry']}</div>
      <div class="sb-price">{info['price']}</div>
      <span class="sb-change {change_class}">{change_prefix}{info['change']}%</span>
    </div>
  </div>
  <nav class="sidebar-nav">
    {nav_items}
  </nav>
  <div class="gen-time">生成于 {datetime.now().strftime('%Y-%m-%d %H:%M')}</div>
  <div class="sidebar-footer">
    <button class="theme-btn" onclick="document.body.classList.toggle('light-mode')">◑ 切换主题</button>
  </div>
</aside>

<!-- MAIN CONTENT -->
<div class="main">

  <!-- HERO OVERVIEW -->
  <section id="overview" class="hero">
    <div class="hero-label">ZBS 深度研究</div>
    <h1 class="hero-title">{info['name']}</h1>
    <p class="hero-sub">{info['business'][:60]}{'…' if len(info['business'])>60 else ''}</p>
    <div class="kpi-strip">
      <div class="kpi-card">
        <div class="kv {'red' if float(info['change'])>0 else 'green'}">{info['price']}</div>
        <div class="kl">最新价</div>
        <div class="ks" style="color:var(--{'red' if float(info['change'])>0 else 'green'})">{change_prefix}{info['change']}%</div>
      </div>
      <div class="kpi-card">
        <div class="kv accent">{target_info['buy_low']}-{target_info['buy_high']}</div>
        <div class="kl">建议买入价</div>
        <div class="ks">分批建仓区间</div>
      </div>
      <div class="kpi-card">
        <div class="kv" style="color:var(--green)">{target_info['sell_price']}-{target_info['sell_high']}</div>
        <div class="kl">建议卖出价</div>
        <div class="ks">目标止盈区间</div>
      </div>
      <div class="kpi-card">
        <div class="kv red">{target_info['stop_loss']}</div>
        <div class="kl">止损价</div>
        <div class="ks">跌破即离场</div>
      </div>
    </div>
  </section>

  <div class="content-wrap">

    <!-- PROFILE -->
    <div id="profile" class="profile-row">
      <div class="card">
        <div class="card-title"><span class="ico">◉</span> 公司画像</div>
        <div class="profile-content">
          <p><strong>主营业务：</strong>{info['business']}</p>
          <div class="profile-tags">
            <span class="tag">{info['industry']}</span>
            <span class="tag">市值 {info['market_cap']}</span>
          </div>
        </div>
      </div>
      <div class="card">
        <div class="card-title"><span class="ico">◉</span> 近期动态</div>
        <div class="news-list">{news_html}</div>
      </div>
    </div>

    <!-- CHARTS -->
    <div id="charts">
      <div class="chart-row">
        <div class="card">
          <div class="card-title"><span class="ico">◉</span> 业务构成</div>
          <div id="business-pie"></div>
        </div>
        <div class="card">
          <div class="card-title"><span class="ico">◉</span> 行情走势</div>
          <div id="kline-small"></div>
        </div>
      </div>
      <div class="card" style="margin-bottom:40px">
        <div class="card-title"><span class="ico">◉</span> K线与成交量 · 近60日</div>
        <div id="kline-full"></div>
        <div class="kline-info">
          <div class="ki"><div class="kil">买入区间</div><div class="kiv">{target_info['buy_low']}-{target_info['buy_high']}元</div></div>
          <div class="ki"><div class="kil">止损位</div><div class="kiv" style="color:var(--red)">{target_info['stop_loss']}元</div></div>
          <div class="ki"><div class="kil">卖出目标</div><div class="kiv" style="color:var(--green)">{target_info['sell_price']}-{target_info['sell_high']}元</div></div>
        </div>
      </div>
    </div>

    <!-- Part I-V sections with GIANT titles -->
    {sections_html}

    <!-- GLOSSARY -->
    <section id="glossary" class="content-section">
      <div class="section-num">APPENDIX</div>
      <h2 class="section-title">术语表</h2>
      <div class="section-rule"></div>
      <div class="section-content">
        <table class="data-table">
          <thead><tr><th>术语</th><th>全称</th><th>含义</th></tr></thead>
          <tbody>
            <tr><td><strong>PE</strong></td><td>Price-to-Earnings Ratio</td><td>市盈率，股价÷每股收益。越低代表越"便宜"，但不同行业差异很大</td></tr>
            <tr><td><strong>PB</strong></td><td>Price-to-Book Ratio</td><td>市净率，股价÷每股净资产。低于1表示股价低于公司净资产</td></tr>
            <tr><td><strong>EPS</strong></td><td>Earnings Per Share</td><td>每股收益，公司净利润÷总股本，衡量每股盈利能力</td></tr>
            <tr><td><strong>MA</strong></td><td>Moving Average</td><td>移动平均线。MA5=5日均价，MA20=20日均价。短线上穿长线叫"金叉"（看涨）</td></tr>
            <tr><td><strong>MACD</strong></td><td>Moving Average Convergence Divergence</td><td>异同移动平均线。DIF上穿DEA为"金叉"（买入信号），反之为"死叉"</td></tr>
            <tr><td><strong>RSI</strong></td><td>Relative Strength Index</td><td>相对强弱指标。低于30为"超卖"（可能反弹），高于70为"超买"（可能回调）</td></tr>
            <tr><td><strong>KDJ</strong></td><td>Stochastic Oscillator</td><td>随机指标。K线和D线在低位交叉为买入信号</td></tr>
            <tr><td><strong>量比</strong></td><td>Volume Ratio</td><td>今日成交量÷过去5日平均成交量。大于1.5表示放量，小于0.5表示缩量</td></tr>
            <tr><td><strong>换手率</strong></td><td>Turnover Rate</td><td>当日成交量÷流通股本。越高说明交易越活跃</td></tr>
            <tr><td><strong>主力资金</strong></td><td>Institutional Flow</td><td>大单（≥50万元）的净流入/流出。净流入为正表示大资金在买入</td></tr>
            <tr><td><strong>涨停/跌停</strong></td><td>Limit Up/Down</td><td>A股单日涨跌幅限制为±10%（创业板/科创板±20%），触及即停止交易</td></tr>
            <tr><td><strong>前复权</strong></td><td>Forward Adjusted</td><td>以最新价格为基准，往前修正历史价格，消除除权除息的影响</td></tr>
            <tr><td><strong>市值</strong></td><td>Market Capitalization</td><td>股价×总股本。大市值（>500亿）一般更稳定，小市值弹性更大</td></tr>
            <tr><td><strong>净利润</strong></td><td>Net Profit</td><td>公司扣除所有成本、税费后的利润，是最核心的盈利指标</td></tr>
            <tr><td><strong>毛利率</strong></td><td>Gross Margin</td><td>(营收-成本)÷营收。越高说明产品/服务的附加值越高</td></tr>
            <tr><td><strong>ROE</strong></td><td>Return on Equity</td><td>净资产收益率，净利润÷净资产。>15%算优秀，衡量赚钱效率</td></tr>
          </tbody>
        </table>
      </div>
    </section>

  </div><!-- /content-wrap -->
</div><!-- /main -->

<footer>
  <p>ZBS · 数据来源 akshare · 本报告仅供研究参考，不构成投资建议</p>
</footer>

<script>
// ── ECharts theme ──
const isDark = !document.body.classList.contains('light-mode');
const chartTextColor = isDark ? '#9aa0b4' : '#5a6278';
const chartLineColor = isDark ? '#252b3a' : '#dce0e8';

// 饼图
echarts.init(document.getElementById('business-pie')).setOption({{
    tooltip: {{ trigger: 'item', formatter: '{{b}}: {{c}}亿 ({{d}}%)' }},
    legend: {{ bottom: 10, textStyle: {{ fontSize: 12, color: chartTextColor }} }},
    series: [{{
        type: 'pie',
        radius: ['42%', '72%'],
        data: {pie_data},
        label: {{ fontSize: 12, formatter: '{{b}}\\n{{d}}%', color: chartTextColor }},
        color: ['#3b82f6','#8b5cf6','#06b6d4','#10b981','#f59e0b','#f43f5e'],
        itemStyle: {{ borderColor: 'var(--bg,#090c14)', borderWidth: 2 }}
    }}]
}});

// K线小图
echarts.init(document.getElementById('kline-small')).setOption({{
    grid: {{ left: '12%', right: '8%', top: '10%', bottom: '25%' }},
    xAxis: {{ type: 'category', data: {dates}, axisLabel: {{ rotate: 45, fontSize: 11, color: chartTextColor }}, axisLine: {{ lineStyle: {{ color: chartLineColor }} }} }},
    yAxis: {{ scale: true, axisLabel: {{ color: chartTextColor }}, splitLine: {{ lineStyle: {{ color: chartLineColor }} }} }},
    tooltip: {{ trigger: 'axis' }},
    series: [{{
        type: 'candlestick',
        data: {ohlc},
        itemStyle: {{ color: '#f43f5e', color0: '#10b981', borderColor: '#f43f5e', borderColor0: '#10b981' }}
    }}]
}});

// K线大图（含MA均线）
echarts.init(document.getElementById('kline-full')).setOption({{
    grid: [
        {{ left: '8%', right: '8%', top: '8%', height: '55%' }},
        {{ left: '8%', right: '8%', top: '70%', height: '18%' }}
    ],
    xAxis: [
        {{ type: 'category', data: {dates}, gridIndex: 0, axisLabel: {{ rotate: 45, fontSize: 11, color: chartTextColor }}, axisLine: {{ lineStyle: {{ color: chartLineColor }} }} }},
        {{ type: 'category', data: {dates}, gridIndex: 1, show: false }}
    ],
    yAxis: [
        {{ scale: true, gridIndex: 0, axisLabel: {{ color: chartTextColor }}, splitLine: {{ lineStyle: {{ color: chartLineColor }} }} }},
        {{ scale: true, gridIndex: 1, splitLine: {{ lineStyle: {{ color: chartLineColor }} }} }}
    ],
    dataZoom: [{{ type: 'inside', xAxisIndex: [0, 1] }}],
    tooltip: {{ trigger: 'axis', axisPointer: {{ type: 'cross' }} }},
    legend: {{ data: ['日K', 'MA5', 'MA20', 'MA60'], top: 0, textStyle: {{ color: chartTextColor, fontSize: 12 }} }},
    series: [
        {{ name: '日K', type: 'candlestick', data: {ohlc}, xAxisIndex: 0, yAxisIndex: 0, itemStyle: {{ color: '#f43f5e', color0: '#10b981', borderColor: '#f43f5e', borderColor0: '#10b981' }} }},
        {{ name: 'MA5', type: 'line', data: {ma5_str}, smooth: true, lineStyle: {{ width: 1.5, color: '#3b82f6' }}, showSymbol: false, xAxisIndex: 0, yAxisIndex: 0 }},
        {{ name: 'MA20', type: 'line', data: {ma20_str}, smooth: true, lineStyle: {{ width: 1.5, color: '#10b981' }}, showSymbol: false, xAxisIndex: 0, yAxisIndex: 0 }},
        {{ name: 'MA60', type: 'line', data: {ma60_str}, smooth: true, lineStyle: {{ width: 1.5, color: '#f59e0b' }}, showSymbol: false, xAxisIndex: 0, yAxisIndex: 0 }},
        {{ name: '成交量', type: 'bar', data: {volumes}, xAxisIndex: 1, yAxisIndex: 1, itemStyle: {{ color: 'rgba(59,130,246,0.25)' }} }}
    ]
}});

// ── Sidebar scroll spy ──
const navLinks = document.querySelectorAll('.nav-item');
const sectionEls = document.querySelectorAll('.content-section, .hero, #charts, #profile');
const observer = new IntersectionObserver((entries) => {{
  entries.forEach(e => {{
    if (e.isIntersecting) {{
      navLinks.forEach(l => l.classList.remove('active'));
      const id = e.target.id;
      const link = document.querySelector(`.nav-item[href="#${{id}}"]`);
      if (link) link.classList.add('active');
    }}
  }});
}}, {{ rootMargin: '-20% 0px -70% 0px' }});
sectionEls.forEach(s => {{ if(s.id) observer.observe(s); }});

// ── Sidebar smooth scroll ──
navLinks.forEach(link => {{
  link.addEventListener('click', function(e) {{
    e.preventDefault();
    const href = this.getAttribute('href');
    if (href && href.startsWith('#')) {{
      const target = document.getElementById(href.slice(1));
      if (target) target.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
    }}
    // close mobile sidebar
    document.querySelector('.sidebar').classList.remove('open');
    document.querySelector('.ham').classList.remove('on');
    document.querySelector('.mob-overlay').classList.remove('on');
  }});
}});

// ── ResizeObserver for charts ──
const ro = new ResizeObserver(() => {{
  document.querySelectorAll('[id^="business-pie"],[id^="kline"]').forEach(el => {{
    const inst = echarts.getInstanceByDom(el);
    if (inst) inst.resize();
  }});
}});
ro.observe(document.querySelector('.main'));
</script>
</body>
</html>'''

    output_dir = os.path.dirname(os.path.abspath(json_file))
    output_file = os.path.join(output_dir, f"zbs-{info['name']}.html")
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html)

    return output_file

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 4:
        print("用法: python phase3_html_renderer_v8.py <股票代码> <md文件> <json文件>")
        sys.exit(1)

    html_file = generate_html(sys.argv[1], sys.argv[2], sys.argv[3])
    print(f"✅ HTML已生成：{html_file}")
