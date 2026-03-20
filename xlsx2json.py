#!/usr/bin/env python3
"""
xlsx2json.py — 一键将 Embodied-R1.5.xlsx 转换为网站所需的 JSON 数据文件。

用法:
    python3 xlsx2json.py                          # 使用默认路径
    python3 xlsx2json.py --xlsx path/to/file.xlsx  # 指定 xlsx 文件

输出:
    assets/data/vlm_benchmarks.json   — VLM 柱状图数据 (来自 VLM-Nano sheet)
    assets/data/vla_benchmarks.json   — VLA 柱状图数据 (来自 VLA sheet)

注意: Compare sheet 的数据目前是内联在 index.html 中的，脚本也会自动更新它。
"""

import argparse
import json
import os
import re
import sys
import zipfile
import xml.etree.ElementTree as ET

# ─── xlsx 解析器 (不依赖 openpyxl 样式, 直接解析 XML) ────────────────────────

def parse_xlsx(filepath):
    """解析 xlsx 文件, 返回 {sheet_name: [[cell, ...], ...]} 的字典"""
    z = zipfile.ZipFile(filepath)
    ns = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    ns_r = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
    ns_pkg = 'http://schemas.openxmlformats.org/package/2006/relationships'

    # 1. 读取 shared strings
    strings = []
    try:
        ss_tree = ET.parse(z.open('xl/sharedStrings.xml'))
        for si in ss_tree.findall(f'.//{{{ns}}}si'):
            parts = []
            for t in si.iter(f'{{{ns}}}t'):
                if t.text:
                    parts.append(t.text)
            strings.append(''.join(parts))
    except KeyError:
        pass

    # 2. 构建 rId -> 文件路径 映射
    wb_rels = ET.parse(z.open('xl/_rels/workbook.xml.rels'))
    rid_map = {}
    for rel in wb_rels.findall(f'.//{{{ns_pkg}}}Relationship'):
        rid_map[rel.attrib['Id']] = rel.attrib['Target']

    # 3. 读取 sheet 名称和路径
    wb_tree = ET.parse(z.open('xl/workbook.xml'))
    sheets_info = {}
    for s in wb_tree.findall(f'.//{{{ns}}}sheet'):
        rid = s.attrib[f'{{{ns_r}}}id']
        target = rid_map[rid]
        path = target if target.startswith('xl/') else 'xl/' + target
        sheets_info[s.attrib['name']] = path

    # 4. 列名转数字 (A=0, B=1, ..., Z=25, AA=26, ...)
    def col_to_idx(col_str):
        result = 0
        for ch in col_str:
            result = result * 26 + (ord(ch) - ord('A') + 1)
        return result - 1

    # 5. 解析每个 sheet
    result = {}
    for name, path in sheets_info.items():
        tree = ET.parse(z.open(path))
        rows_data = []
        for row_el in tree.findall(f'.//{{{ns}}}row'):
            cells = {}
            for c in row_el.findall(f'{{{ns}}}c'):
                ref = c.attrib['r']
                col_str = re.match(r'([A-Z]+)', ref).group(1)
                col_idx = col_to_idx(col_str)
                t = c.attrib.get('t', '')
                v = c.find(f'{{{ns}}}v')
                if v is not None and v.text is not None:
                    if t == 's':
                        val = strings[int(v.text)]
                    else:
                        try:
                            val = float(v.text)
                        except ValueError:
                            val = v.text
                    cells[col_idx] = val
                else:
                    cells[col_idx] = None
            rows_data.append(cells)
        result[name] = rows_data

    z.close()
    return result


def get_cell(rows, r, c, default=None):
    """安全获取某行某列的值"""
    if r < len(rows):
        return rows[r].get(c, default)
    return default


def round_val(v, decimals=1):
    """将数值四舍五入, 非数值返回原值"""
    if isinstance(v, (int, float)):
        r = round(v, decimals)
        return int(r) if r == int(r) else r
    return v


# ─── VLM-Nano → vlm_benchmarks.json ──────────────────────────────────────────

# 模型配置 (name 必须与 xlsx 中 A 列完全匹配)
VLM_MODEL_CONFIG = [
    {"xlsx_name": "Embodied-R1.5",         "name": "Embodied-R1.5",         "short": "ER1.5",    "group": "ours",      "logo": "./logo/ER1.5-logo3.png", "color": "#2563eb"},
    {"xlsx_name": "Embodied-R1",            "name": "Embodied-R1",            "short": "ER1",      "group": "embodied",  "logo": "./logo/ER1.5-logo3.png", "color": "#7cb3ff"},
    {"xlsx_name": "Gemini-Robotics-ER-1.5", "name": "Gemini-Robotics-1.5",    "short": "GR-1.5",  "group": "generalist","logo": "./logo/gemini.jpeg",     "color": "#4b5563"},
    {"xlsx_name": "Gemini-2.5-Pro",         "name": "Gemini-2.5-Pro",         "short": "Gemini-2.5","group": "generalist","logo": "./logo/gemini.jpeg",    "color": "#7c8494"},
    {"xlsx_name": "GPT-5.4",                "name": "GPT-5.4",                "short": "GPT-5.4",  "group": "generalist","logo": "./logo/openai.png",      "color": "#a3aab6"},
    {"xlsx_name": "Mimo-Embodied",          "name": "Mimo-Embodied",          "short": "Mimo",     "group": "embodied",  "logo": "./logo/xiaomi.png",      "color": "#c9cdd4"},
]

# VLM benchmark 列映射 (列号从 0 开始: A=0, B=1, C=2, ...)
# 行1是 benchmark 名, 从 C(2) 到 Y(24)
VLM_BENCHMARKS_COLS = {
    # Embodied Cognition and Spatial Reasoning
    "ERQA":     2,   # C
    "OpenEQA":  3,   # D
    "CV-Bench": 4,   # E
    "EmbSpatial": 5, # F
    "SAT":      6,   # G
    "RoboSpatial": 7,# H
    "BLINK (Rel. Depth)": 8,  # I
    # Embodied Pointing and Location
    "VAbench-P":    11, # L
    "Where2Place":  12, # M
    "RefSpatial":   13, # N
    "Part-Afford":  14, # O
    "RoboRefit":    15, # P
    "RoboAfford":   16, # Q
    "PIO":          18, # S
    "Pixmo-Point":  19, # T
    # Embodied Planning and Correction
    "RoboVQA":  21, # V
    "EgoPlan2": 22, # W
    "Cosmos":   23, # X
    "RoboFAC":  24, # Y
}

# 三大类 overall 列
VLM_OVERALL_COLS = {
    "Embodied Cognition and Spatial Reasoning\n7 Benchmarks": 10,  # K
    "Embodied Pointing and Location\n8 Benchmarks": 20,            # U  (注: 实际是9 tasks)
    "Embodied Planning and Correction\n4 Benchmarks": 25,          # Z
}

VLM_FEATURED = ["ERQA", "OpenEQA", "VAbench-P", "RoboVQA"]


def build_vlm_json(sheets):
    """从 VLM-Nano sheet 构建 vlm_benchmarks.json"""
    rows = sheets['VLM-Nano']

    # 找到每个模型的行号
    model_rows = {}
    for i, row in enumerate(rows):
        name = row.get(0)  # A 列
        if name:
            name = name.strip()
            model_rows[name] = i

    # 构建 models 列表
    models = []
    for cfg in VLM_MODEL_CONFIG:
        models.append({
            "name": cfg["name"],
            "short": cfg["short"],
            "group": cfg["group"],
            "logo": cfg["logo"],
            "color": cfg["color"],
        })

    # 构建 overalls
    overalls = {}
    for label, col in VLM_OVERALL_COLS.items():
        scores = []
        for cfg in VLM_MODEL_CONFIG:
            row_idx = model_rows.get(cfg["xlsx_name"])
            if row_idx is not None:
                val = get_cell(rows, row_idx, col)
                # 如果 Overall 为 None, 需要计算
                if val is None:
                    # 根据 label 确定哪些 benchmark 列参与计算
                    if "Cognition" in label:
                        cols = [2, 3, 4, 5, 6, 7, 8]  # C-I (不含 VSIBench=J=9)
                    elif "Pointing" in label:
                        cols = [11, 12, 13, 14, 15, 16, 18, 19]  # L-T (不含 PointBench=R=17)
                    elif "Planning" in label:
                        cols = [21, 22, 23, 24]  # V-Y
                    else:
                        cols = []
                    vals = [get_cell(rows, row_idx, c) for c in cols]
                    vals = [v for v in vals if isinstance(v, (int, float))]
                    val = round(sum(vals) / len(vals), 1) if vals else 0
                scores.append(round_val(val))
            else:
                scores.append(0)
                print(f"  ⚠️  VLM-Nano 中找不到模型: {cfg['xlsx_name']}")
        overalls[label] = scores

    # 构建 all_benchmarks
    all_benchmarks = {}
    for bm_name, col in VLM_BENCHMARKS_COLS.items():
        scores = []
        for cfg in VLM_MODEL_CONFIG:
            row_idx = model_rows.get(cfg["xlsx_name"])
            if row_idx is not None:
                val = get_cell(rows, row_idx, col, 0)
                scores.append(round_val(val if val is not None else 0))
            else:
                scores.append(0)
        all_benchmarks[bm_name] = scores

    return {
        "models": models,
        "featured": VLM_FEATURED,
        "overalls": overalls,
        "all_benchmarks": all_benchmarks,
    }


# ─── VLA → vla_benchmarks.json ───────────────────────────────────────────────

# VLA sheet 的结构:
# 第一个表 (google_robot_vm): 从 "Simpler-Google" 开头行开始
# 需要识别每个子表的起始行

VLA_MODEL_NAME_MAP = {
    '𝜋0': 'pi0',
    '𝜋0-FAST': 'pi0-FAST',
    '𝜋0.5': 'pi0.5',
}


def normalize_model_name(name):
    """将 xlsx 中的 unicode 模型名映射为 JSON 中的名称"""
    if name in VLA_MODEL_NAME_MAP:
        return VLA_MODEL_NAME_MAP[name]
    return name


def build_vla_json(sheets):
    """从 VLA sheet 构建 vla_benchmarks.json"""
    rows = sheets['VLA']

    # 识别各个子表的起始行
    sections = []
    for i, row in enumerate(rows):
        val = row.get(0)
        if val and isinstance(val, str):
            val_clean = val.strip().replace('\n', ' ')
            if any(keyword in val_clean for keyword in ['Simpler-Google', 'Simpler-WidowX', 'LIBERO Benchmark', 'LIBERO-Plus']):
                sections.append((i, val_clean))

    result = {}

    for sec_idx, (start_row, title) in enumerate(sections):
        # 确定结束行
        end_row = sections[sec_idx + 1][0] if sec_idx + 1 < len(sections) else len(rows)

        # 读取 header (tasks)
        header_row = rows[start_row]
        # B 列开始是 task 名
        tasks = []
        col = 1
        while True:
            val = header_row.get(col)
            if val is None and col > 8:
                break
            if val is not None:
                tasks.append(str(val).strip())
            col += 1
            if col > 20:
                break

        # 判断是否是 LIBERO (有分组)
        is_libero = 'LIBERO Benchmark' in title
        is_libero_plus = 'LIBERO-Plus' in title

        if is_libero:
            # LIBERO 有分组: "W/ Action Pretraining" (Pt.=Y) 和 "W/O Action Pretraining" (Pt.=N)
            # tasks 从 C(2) 开始: Goal, Spatial, Object, Long, Overall
            tasks_clean = []
            for c in range(2, 7):  # C=2 to G=6
                v = header_row.get(c)
                if v:
                    tasks_clean.append(str(v).strip())
            tasks = tasks_clean

            groups = {"W/ Action Pretraining": {}, "W/O Action Pretraining": {}}
            for r in range(start_row + 1, end_row):
                row = rows[r]
                model = row.get(0)
                pt = row.get(1)  # B 列: Y/N
                if model is None or not isinstance(model, str) or model.strip() == '':
                    continue
                model = normalize_model_name(model.strip())
                scores = []
                for c in range(2, 2 + len(tasks)):
                    v = row.get(c)
                    scores.append(round_val(v) if isinstance(v, (int, float)) else None)

                # 如果最后一个 task 是 "Overall" 且值为 None, 自动计算
                if tasks and tasks[-1] == 'Overall' and scores and scores[-1] is None:
                    numeric = [s for s in scores[:-1] if isinstance(s, (int, float))]
                    if numeric:
                        scores[-1] = round_val(round(sum(numeric) / len(numeric), 1))

                if pt == 'Y':
                    groups["W/ Action Pretraining"][model] = scores
                elif pt == 'N':
                    groups["W/O Action Pretraining"][model] = scores

            result['libero'] = {
                "title": "LIBERO Benchmark",
                "tasks": tasks,
                "groups": groups,
            }

        elif is_libero_plus:
            # LIBERO-Plus: 无分组, 直接 model -> scores
            tasks_clean = []
            for c in range(1, 9):  # B=1 to I=8
                v = header_row.get(c)
                if v:
                    tasks_clean.append(str(v).strip())
            tasks = tasks_clean

            models_data = {}
            for r in range(start_row + 1, end_row):
                row = rows[r]
                model = row.get(0)
                if model is None or not isinstance(model, str) or model.strip() == '':
                    continue
                model = normalize_model_name(model.strip())
                scores = []
                for c in range(1, 1 + len(tasks)):
                    v = row.get(c)
                    scores.append(round_val(v) if isinstance(v, (int, float)) else None)
                models_data[model] = scores

            result['libero_plus'] = {
                "title": "LIBERO-Plus Benchmark",
                "tasks": tasks,
                "models": models_data,
            }

        else:
            # Simpler 类型: 普通 model -> scores
            tasks_clean = []
            for c in range(1, 7):  # B=1 to F=5
                v = header_row.get(c)
                if v:
                    tasks_clean.append(str(v).strip())
            tasks = tasks_clean

            models_data = {}
            for r in range(start_row + 1, end_row):
                row = rows[r]
                model = row.get(0)
                if model is None or not isinstance(model, str) or model.strip() == '':
                    continue
                model = normalize_model_name(model.strip())
                scores = []
                for c in range(1, 1 + len(tasks)):
                    v = row.get(c)
                    scores.append(round_val(v) if isinstance(v, (int, float)) else None)
                # 如果最后一个 task 是 "Overall" 且值为 None, 自动计算
                if tasks and tasks[-1] == 'Overall' and (len(scores) == 0 or scores[-1] is None):
                    numeric = [s for s in scores[:-1] if isinstance(s, (int, float))]
                    if numeric:
                        avg = round(sum(numeric) / len(numeric), 1)
                        if len(scores) > 0:
                            scores[-1] = round_val(avg)
                        else:
                            scores.append(round_val(avg))
                models_data[model] = scores

            # 确定 key
            if 'Visual Matching' in title and 'Google' in title:
                key = 'google_robot_vm'
                display_title = "Simpler-Google Robot (Visual Matching)"
            elif 'Visual Aggregation' in title or 'Variant' in title:
                key = 'google_robot_va'
                display_title = "Simpler-Google Robot (Variant Aggregation)"
            elif 'WidowX' in title:
                key = 'widowx'
                display_title = "Simpler-WidowX (Visual Matching)"
            else:
                key = title.lower().replace(' ', '_')
                display_title = title

            result[key] = {
                "title": display_title,
                "tasks": tasks,
                "models": models_data,
            }

    return result


# ─── VLM-Full → vlm_full.json ────────────────────────────────────────────────

def build_vlm_full_json(sheets):
    """从 VLM-Full sheet 构建 vlm_full.json — 完整 leaderboard 表格数据"""
    rows = sheets['VLM-Full']

    # 列映射 (row 1)
    benchmarks = [
        # col, name, split
        (2, 'ERQA', ''),
        (3, 'OpenEQA', ''),
        (4, 'CV-Bench', 'All'),
        (5, 'EmbSpatial', 'Test'),
        (6, 'SAT', 'Test'),
        (7, 'RoboSpatial', 'All'),
        (8, 'BLINK', 'Rel. Depth'),
        (9, 'VSIBench', ''),
        (10, 'Overall', '8 Tasks'),
        (11, 'VAbench-P', ''),
        (12, 'Where2Place', ''),
        (13, 'RefSpatial', 'L/P/U'),
        (14, 'Part-Afford', ''),
        (15, 'RoboRefit', 'Test'),
        (16, 'RoboAfford', 'Test'),
        (17, 'PointBench', 'All'),
        (18, 'PIO', 'S1&S2'),
        (19, 'Pixmo-Point', 'Test'),
        (20, 'Overall', '9 Tasks'),
        (21, 'RoboVQA', 'Test'),
        (22, 'EgoPlan2', ''),
        (23, 'Cosmos', 'Reason'),
        (24, 'RoboFAC', 'Test'),
        (25, 'Overall', '4 Tasks'),
    ]

    # 类别分组
    categories = [
        {"name": "Embodied Cognition and Spatial Reasoning", "start": 0, "end": 9},  # ERQA .. Overall(8)
        {"name": "Embodied Pointing and Location", "start": 9, "end": 19},  # VAbench-P .. Overall(9)
        {"name": "Embodied Planning and Correction", "start": 19, "end": 24},  # RoboVQA .. Overall(4)
    ]

    # 分组 row 标记: row 3 = "Generlist", row 12 = "Open Sourced Embodied"
    groups = []  # (group_name, models_list)
    current_group = None
    current_models = []

    for r in range(3, len(rows)):
        row = rows[r]
        name = row.get(0)
        if name is None or (isinstance(name, str) and name.strip() == ''):
            continue
        name_str = str(name).strip()

        # 是否是分组标题行 (没有数据列)
        has_data = any(isinstance(row.get(c), (int, float)) for c in range(2, 26))
        if not has_data:
            # 保存上一个组
            if current_group is not None and current_models:
                groups.append({"group": current_group, "models": current_models})
            current_group = name_str
            current_models = []
            continue

        # 模型数据行
        institution = row.get(1, '')
        if institution is None:
            institution = ''
        institution = str(institution).strip()

        scores = []
        for col, bm_name, split in benchmarks:
            v = row.get(col)
            if isinstance(v, (int, float)):
                scores.append(round_val(v, 2))
            else:
                scores.append(None)

        # 计算 Overall 列 (如果为 None)
        # Overall col 10 = mean of cols 2-9
        if scores[8] is None:  # Overall (8 Tasks) at index 8
            vals = [s for s in scores[0:8] if s is not None]
            if vals:
                scores[8] = round_val(round(sum(vals) / len(vals), 1))
        # Overall col 20 = mean of cols 11-19
        if scores[18] is None:  # Overall (9 Tasks) at index 18
            vals = [s for s in scores[9:18] if s is not None]
            if vals:
                scores[18] = round_val(round(sum(vals) / len(vals), 1))
        # Overall col 25 = mean of cols 21-24
        if scores[23] is None:  # Overall (4 Tasks) at index 23
            vals = [s for s in scores[19:23] if s is not None]
            if vals:
                scores[23] = round_val(round(sum(vals) / len(vals), 1))

        current_models.append({
            "name": name_str,
            "institution": institution,
            "scores": scores,
        })

    # 最后一个组
    if current_group is not None and current_models:
        groups.append({"group": current_group, "models": current_models})

    return {
        "benchmarks": [{"name": n, "split": s} for _, n, s in benchmarks],
        "categories": categories,
        "groups": groups,
    }


# ─── VLM-Trace → vlm_trace.json ─────────────────────────────────────────────

def build_vlm_trace_json(sheets):
    """从 VLM-Trace sheet 构建 vlm_trace.json"""
    rows = sheets['VLM-Trace']

    # 列: 2=ShareRobot-V RMSE↓, 3=ShareRobot-V DFD↓, 4=VABench-V RMSE↓, 5=VABench-V DFD↓, 6=PIO-S3 GPT-Score↑
    benchmarks = [
        {"name": "ShareRobot-V RMSE", "lower_is_better": True},
        {"name": "ShareRobot-V DFD", "lower_is_better": True},
        {"name": "VABench-V RMSE", "lower_is_better": True},
        {"name": "VABench-V DFD", "lower_is_better": True},
        {"name": "PIO-S3 GPT-Score", "lower_is_better": False},
    ]

    groups = []
    current_group = None
    current_models = []

    for r in range(3, len(rows)):
        row = rows[r]
        name = row.get(0)
        if name is None or (isinstance(name, str) and name.strip() == ''):
            continue
        name_str = str(name).strip()

        has_data = any(isinstance(row.get(c), (int, float)) for c in range(2, 7))
        if not has_data:
            if current_group is not None and current_models:
                groups.append({"group": current_group, "models": current_models})
            current_group = name_str
            current_models = []
            continue

        institution = row.get(1, '')
        if institution is None:
            institution = ''
        institution = str(institution).strip()

        scores = []
        for c in range(2, 7):
            v = row.get(c)
            scores.append(round_val(v, 2) if isinstance(v, (int, float)) else None)

        current_models.append({
            "name": name_str,
            "institution": institution,
            "scores": scores,
        })

    if current_group is not None and current_models:
        groups.append({"group": current_group, "models": current_models})

    return {
        "benchmarks": benchmarks,
        "groups": groups,
    }


# ─── GeneralBenchmark → general_benchmark.json ──────────────────────────────

def build_general_benchmark_json(sheets):
    """从 GeneralBenchmark sheet 构建 general_benchmark.json"""
    rows = sheets['GeneralBenchmark']

    # Row 0: header names (cols 1-7)
    # Row 1: split names
    # Row 2+: model data
    benchmarks = []
    for c in range(1, 8):
        name = rows[0].get(c, '')
        split = rows[1].get(c, '')
        if name:
            benchmarks.append({"name": str(name).strip(), "split": str(split).strip() if split else ''})

    models = []
    for r in range(2, len(rows)):
        row = rows[r]
        name = row.get(0)
        if name is None or (isinstance(name, str) and name.strip() == ''):
            continue
        scores = []
        for c in range(1, 1 + len(benchmarks)):
            v = row.get(c)
            scores.append(round_val(v, 1) if isinstance(v, (int, float)) else None)
        models.append({"name": str(name).strip(), "scores": scores})

    return {
        "benchmarks": benchmarks,
        "models": models,
    }


# ─── Real-World → realworld.json ────────────────────────────────────────────

def build_realworld_json(sheets):
    """从 Real-World sheet 构建 realworld.json"""
    rows = sheets['Real-World']

    # Row 0: task headers (cols 1-5)
    tasks = []
    for c in range(1, 6):
        v = rows[0].get(c)
        if v:
            tasks.append(str(v).strip())

    models = []
    for r in range(1, len(rows)):
        row = rows[r]
        name = row.get(0)
        if name is None or (isinstance(name, str) and name.strip() == ''):
            continue
        scores = []
        for c in range(1, 1 + len(tasks)):
            v = row.get(c)
            if isinstance(v, (int, float)):
                scores.append(round_val(v, 1))
            elif isinstance(v, str) and v.strip() == '-':
                scores.append('-')
            else:
                scores.append(None)
        models.append({"name": str(name).strip(), "scores": scores})

    return {
        "tasks": tasks,
        "models": models,
    }


# ─── SFT Dataset → sft_dataset.json ─────────────────────────────────────────

def build_sft_dataset_json(sheets):
    """从 Embodied-R1.5-SFT-Dataset sheet 构建 sft_dataset.json"""
    rows = sheets['Embodied-R1.5-SFT-Dataset']

    # 分类覆盖：修正 xlsx 中的分类错误
    TYPE_OVERRIDES = {
        'LLaVA-1.5-665K': 'General Knowledge',
    }

    # Row 0: header, Row 1+: data
    # Cols: A=name, B=used, C=all, D=all_conversations, E=type
    datasets = []
    total = 0
    for r in range(1, len(rows)):
        row = rows[r]
        name = row.get(0)
        if name is None or (isinstance(name, str) and name.strip() == ''):
            continue
        used = row.get(1)
        dtype = row.get(4, '')
        if used is None or not isinstance(used, (int, float)):
            continue
        used = int(used)
        total += used
        name_str = str(name).strip()
        type_str = TYPE_OVERRIDES.get(name_str, str(dtype).strip() if dtype else '')
        datasets.append({
            "name": name_str,
            "count": used,
            "type": type_str,
        })

    # 按 type 分组
    type_groups = {}
    for d in datasets:
        t = d['type']
        if t not in type_groups:
            type_groups[t] = []
        type_groups[t].append({"name": d['name'], "count": d['count']})

    groups = []
    for t, items in type_groups.items():
        group_total = sum(i['count'] for i in items)
        groups.append({
            "type": t,
            "total": group_total,
            "percentage": round(group_total / total * 100, 1) if total > 0 else 0,
            "datasets": items,
        })

    return {
        "total": total,
        "groups": groups,
    }


# ─── RFT Dataset → rft_dataset.json ─────────────────────────────────────────

def build_rft_dataset_json(sheets):
    """从 Embodied-R1.5-RFT-Dataset sheet 构建 rft_dataset.json"""
    rows = sheets['Embodied-R1.5-RFT-Dataset']

    datasets = []
    total = 0
    for r in range(1, len(rows)):
        row = rows[r]
        name = row.get(0)
        if name is None or (isinstance(name, str) and name.strip() == ''):
            continue
        data_type = row.get(1, '')
        used = row.get(2)
        dtype = row.get(3, '')
        if used is None or not isinstance(used, (int, float)):
            continue
        used = int(used)
        total += used
        datasets.append({
            "name": str(name).strip(),
            "data_type": str(data_type).strip() if data_type else '',
            "count": used,
            "type": str(dtype).strip() if dtype else '',
        })

    # 按 type 分组
    type_groups = {}
    for d in datasets:
        t = d['type']
        if t not in type_groups:
            type_groups[t] = []
        type_groups[t].append({"name": d['name'], "data_type": d['data_type'], "count": d['count']})

    groups = []
    for t, items in type_groups.items():
        group_total = sum(i['count'] for i in items)
        groups.append({
            "type": t,
            "total": group_total,
            "percentage": round(group_total / total * 100, 1) if total > 0 else 0,
            "datasets": items,
        })

    return {
        "total": total,
        "groups": groups,
    }


# ─── Compare → 更新 index.html 中的内联数据 ──────────────────────────────────

def build_compare_data(sheets):
    """从 Compare sheet 构建 LIBERO backbone 对比数据"""
    rows = sheets['Compare']

    # 结构: Action Expert | VLM Backbone | Steps | Goal | Spatial | Object | Long | Overall
    # GR00T 组和 OFT 组

    groot_data = {}
    oft_data = {}
    steps_set = []

    current_expert = None
    for r in range(1, len(rows)):
        row = rows[r]
        expert = row.get(0)
        if expert and isinstance(expert, str) and expert.strip():
            current_expert = expert.strip()
        backbone = row.get(1)
        step = row.get(2)
        if backbone is None or step is None:
            continue
        backbone = str(backbone).strip()
        step = str(step).strip()

        # 计算 Overall = mean(Goal, Spatial, Object, Long)
        vals = []
        for c in range(3, 7):  # D=3, E=4, F=5, G=6
            v = row.get(c)
            if isinstance(v, (int, float)):
                vals.append(v)
        if not vals:
            continue

        overall = round(sum(vals) / len(vals), 2)
        # 如果数据是百分比形式(0-1), 转成 0-100
        if all(v <= 1 for v in vals):
            overall_pct = round(overall * 100, 2)
        else:
            overall_pct = overall

        if step not in steps_set:
            steps_set.append(step)

        target = groot_data if current_expert == 'GR00T' else oft_data
        if backbone not in target:
            target[backbone] = []
        target[backbone].append(overall_pct)

    return {
        "steps": steps_set,
        "groot": groot_data,
        "oft": oft_data,
    }


def update_index_html(compare_data, base_dir):
    """更新 index.html 中的 LIBERO backbone 对比内联数据"""
    html_path = os.path.join(base_dir, 'index.html')
    if not os.path.exists(html_path):
        print("  ⚠️  index.html 不存在, 跳过内联数据更新")
        return False

    with open(html_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 匹配 const data = { steps: [...], groot: {...}, oft: {...} };
    pattern = r"(const data = \{)\s*steps:.*?(\};\s*const colors)"

    # 构建新的数据块
    steps_str = json.dumps(compare_data['steps'])

    groot_lines = []
    for name, vals in compare_data['groot'].items():
        groot_lines.append(f"            '{name}': {json.dumps(vals)}")

    oft_lines = []
    for name, vals in compare_data['oft'].items():
        oft_lines.append(f"            '{name}': {json.dumps(vals)}")

    new_data = f"""const data = {{
          steps: {steps_str},
          groot: {{
{(',' + chr(10)).join(groot_lines)}
          }},
          oft: {{
{(',' + chr(10)).join(oft_lines)}
          }}
        }};
        const colors"""

    new_content = re.sub(pattern, new_data, content, flags=re.DOTALL)

    if new_content != content:
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        return True
    return False


# ─── 主函数 ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='将 Embodied-R1.5.xlsx 转换为网站 JSON 数据')
    parser.add_argument('--xlsx', default='Embodied-R1.5.xlsx', help='xlsx 文件路径')
    parser.add_argument('--output-dir', default='assets/data', help='JSON 输出目录')
    parser.add_argument('--no-html', action='store_true', help='不更新 index.html 中的内联数据')
    args = parser.parse_args()

    # 确定基础目录
    base_dir = os.path.dirname(os.path.abspath(args.xlsx))
    xlsx_path = os.path.abspath(args.xlsx)
    output_dir = os.path.join(base_dir, args.output_dir)

    if not os.path.exists(xlsx_path):
        print(f"❌ 找不到文件: {xlsx_path}")
        sys.exit(1)

    os.makedirs(output_dir, exist_ok=True)

    print(f"📊 解析 {os.path.basename(xlsx_path)} ...")
    sheets = parse_xlsx(xlsx_path)
    print(f"   找到 {len(sheets)} 个工作表: {', '.join(sheets.keys())}")

    # 1. VLM benchmarks
    print("\n📈 生成 vlm_benchmarks.json (来自 VLM-Nano) ...")
    vlm_data = build_vlm_json(sheets)
    vlm_path = os.path.join(output_dir, 'vlm_benchmarks.json')
    with open(vlm_path, 'w', encoding='utf-8') as f:
        json.dump(vlm_data, f, indent=2, ensure_ascii=False)
    n_models = len(vlm_data['models'])
    n_benchmarks = len(vlm_data['all_benchmarks'])
    print(f"   ✅ {n_models} 个模型, {n_benchmarks} 个 benchmarks → {vlm_path}")

    # 2. VLA benchmarks
    print("\n🤖 生成 vla_benchmarks.json (来自 VLA) ...")
    vla_data = build_vla_json(sheets)
    vla_path = os.path.join(output_dir, 'vla_benchmarks.json')
    with open(vla_path, 'w', encoding='utf-8') as f:
        json.dump(vla_data, f, indent=2, ensure_ascii=False)
    sections = list(vla_data.keys())
    print(f"   ✅ {len(sections)} 个部分: {', '.join(sections)} → {vla_path}")

    # 3. VLM-Full → vlm_full.json
    print("\n📊 生成 vlm_full.json (来自 VLM-Full) ...")
    vlm_full_data = build_vlm_full_json(sheets)
    vlm_full_path = os.path.join(output_dir, 'vlm_full.json')
    with open(vlm_full_path, 'w', encoding='utf-8') as f:
        json.dump(vlm_full_data, f, indent=2, ensure_ascii=False)
    total_models = sum(len(g['models']) for g in vlm_full_data['groups'])
    print(f"   ✅ {total_models} 个模型, {len(vlm_full_data['benchmarks'])} 个 benchmarks → {vlm_full_path}")

    # 4. VLM-Trace → vlm_trace.json
    print("\n📊 生成 vlm_trace.json (来自 VLM-Trace) ...")
    vlm_trace_data = build_vlm_trace_json(sheets)
    vlm_trace_path = os.path.join(output_dir, 'vlm_trace.json')
    with open(vlm_trace_path, 'w', encoding='utf-8') as f:
        json.dump(vlm_trace_data, f, indent=2, ensure_ascii=False)
    total_trace = sum(len(g['models']) for g in vlm_trace_data['groups'])
    print(f"   ✅ {total_trace} 个模型, {len(vlm_trace_data['benchmarks'])} 个 benchmarks → {vlm_trace_path}")

    # 5. GeneralBenchmark → general_benchmark.json
    print("\n📊 生成 general_benchmark.json (来自 GeneralBenchmark) ...")
    general_data = build_general_benchmark_json(sheets)
    general_path = os.path.join(output_dir, 'general_benchmark.json')
    with open(general_path, 'w', encoding='utf-8') as f:
        json.dump(general_data, f, indent=2, ensure_ascii=False)
    print(f"   ✅ {len(general_data['models'])} 个模型, {len(general_data['benchmarks'])} 个 benchmarks → {general_path}")

    # 6. Real-World → realworld.json
    print("\n📊 生成 realworld.json (来自 Real-World) ...")
    rw_data = build_realworld_json(sheets)
    rw_path = os.path.join(output_dir, 'realworld.json')
    with open(rw_path, 'w', encoding='utf-8') as f:
        json.dump(rw_data, f, indent=2, ensure_ascii=False)
    print(f"   ✅ {len(rw_data['models'])} 个模型, {len(rw_data['tasks'])} 个任务 → {rw_path}")

    # 7. SFT Dataset → sft_dataset.json
    print("\n📊 生成 sft_dataset.json (来自 Embodied-R1.5-SFT-Dataset) ...")
    sft_data = build_sft_dataset_json(sheets)
    sft_path = os.path.join(output_dir, 'sft_dataset.json')
    with open(sft_path, 'w', encoding='utf-8') as f:
        json.dump(sft_data, f, indent=2, ensure_ascii=False)
    print(f"   ✅ {len(sft_data['groups'])} 个类别, 总计 {sft_data['total']} 条 → {sft_path}")

    # 8. RFT Dataset → rft_dataset.json
    print("\n📊 生成 rft_dataset.json (来自 Embodied-R1.5-RFT-Dataset) ...")
    rft_data = build_rft_dataset_json(sheets)
    rft_path = os.path.join(output_dir, 'rft_dataset.json')
    with open(rft_path, 'w', encoding='utf-8') as f:
        json.dump(rft_data, f, indent=2, ensure_ascii=False)
    print(f"   ✅ {len(rft_data['groups'])} 个类别, 总计 {rft_data['total']} 条 → {rft_path}")

    # 9. 更新 index.html 内联数据 (Compare sheet)
    if not args.no_html:
        print("\n🔄 更新 index.html 内联数据 (来自 Compare) ...")
        compare_data = build_compare_data(sheets)
        if update_index_html(compare_data, base_dir):
            print(f"   ✅ index.html 已更新 (LIBERO backbone 对比数据)")
        else:
            print(f"   ℹ️  index.html 无变化或不存在")

    print("\n🎉 全部完成!")


if __name__ == '__main__':
    main()
