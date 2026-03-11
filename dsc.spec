# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for building DSC as a standalone executable.

Build:
    pyinstaller dsc.spec

Output:
    dist/dsc.exe  (Windows)
    dist/dsc      (Linux/macOS)
"""

import sys
from pathlib import Path

block_cipher = None

a = Analysis(
    ['src/dsc/cli/entry.py'],
    pathex=['src'],
    binaries=[],
    datas=[],
    hiddenimports=[
        'dsc',
        'dsc.cli',
        'dsc.cli.main',
        'dsc.models',
        'dsc.models.conditions',
        'dsc.models.graph',
        'dsc.models.project',
        'dsc.models.scenario',
        'dsc.models.trace',
        'dsc.storage',
        'dsc.storage.filesystem',
        'dsc.scenario_manager',
        'dsc.scenario_manager.manager',
        'dsc.trace_collector',
        'dsc.trace_collector.collector',
        'dsc.trace_collector.simulator',
        'dsc.graph_extractor',
        'dsc.graph_extractor.extractor',
        'dsc.graph_optimizer',
        'dsc.graph_optimizer.optimizer',
        'dsc.compiler',
        'dsc.compiler.compiler',
        'dsc.runtime',
        'dsc.runtime.engine',
        'dsc.runtime.evaluator',
        'dsc.llm',
        'dsc.llm.client',
        'dsc.llm.prompts',
        'dsc.analyzer',
        'dsc.analyzer.report',
        'dsc.analyzer.static_analyzer',
        'dsc.analyzer.log_analyzer',
        'dsc.analyzer.cost_estimator',
        'dsc.analyzer.bridge',
        # Dependencies that PyInstaller may miss
        'pydantic',
        'typer',
        'rich',
        'click',
        'anthropic',
        'networkx',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='dsc',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
