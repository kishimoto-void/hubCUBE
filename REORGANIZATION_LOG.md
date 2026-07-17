# hubCUBE Reorganization Log

**日付**: 2026-07-17
**実行者**: Grok (AI assistant) + kishimoto-void
**目的**: ルートレベルのバージョン混在を解消し、ARCHITECTURE.md / DESIGN.md の設計思想に沿ったモジュール構造へ整理。実験の忠実性と可読性を向上させる。

## 整理前 の問題点
- ルートに `CUBE_Anomaly_Detection_v*.py`、`hubCUBE_SingleRole_Template_v*.py` などバージョン付きファイルが多数散在
- 最新推奨ファイル（v4系）と過去バージョンが混在し、ナビゲーションが困難
- ARCHITECTURE.md で提案されている `forces/`、`dynamics/` 等のディレクトリ構造と実装が乖離
- phase_transition_observer/ の一部ファイルが極端に小さい（内容不完全の可能性）

## 実行した整理内容（段階的）

### 1. パッケージディレクトリの作成
- `forces/` : CarryForce 等の純粋 Force Generator を配置
- `templates/` : SingleRoleCUBE テンプレートを配置
- `experiments/` : 過去バージョン・実験的コード・Anomaly Detection 系を移動

### 2. ファイル移動
| 元のパス | 新しいパス | 種別 | 備考 |
|----------|------------|------|------|
| CarryForce_v4.py | forces/CarryForce_v4.py | Core Force | import変更なし |
| hubCUBE_SingleRole_Template_v4_ForceBased.py | templates/hubCUBE_SingleRole_Template_v4_ForceBased.py | Core Template | importを `from forces.CarryForce_v4` に更新 |
| SimpleDynamicsSolver_example.py | experiments/SimpleDynamicsSolver_example.py | Example | import更新 |
| CUBE_Anomaly_Detection_v2.6_Robust.py | experiments/CUBE_Anomaly_Detection_v2.6_Robust.py | Legacy Experiment | - |
| CUBE_Anomaly_Detection_v2.7_Improved.py | experiments/CUBE_Anomaly_Detection_v2.7_Improved.py | Legacy Experiment | - |
| CUBE_Anomaly_Detection_v2.8_Generalized.py | experiments/CUBE_Anomaly_Detection_v2.8_Generalized.py | Legacy Experiment | - |
| CarryField_v3_Minimal.py | experiments/CarryField_v3_Minimal.py | Legacy | - |
| hubCUBE_SingleRole_Template.py | experiments/hubCUBE_SingleRole_Template.py | Legacy Template | - |
| hubCUBE_SingleRole_Template_v2.1_Optimized.py | experiments/hubCUBE_SingleRole_Template_v2.1_Optimized.py | Legacy Template | - |
| hubCUBE_SingleRole_Template_v2.2_ImprovedCarry.py | experiments/hubCUBE_SingleRole_Template_v2.2_ImprovedCarry.py | Legacy Template | - |

### 3. Import修正
- `templates/hubCUBE_SingleRole_Template_v4_ForceBased.py` : `from CarryForce_v4 import CarryForce` → `from forces.CarryForce_v4 import CarryForce`
- `experiments/SimpleDynamicsSolver_example.py` : 同上

### 4. ドキュメント更新
- README.md : 最新推奨パスを更新 + 再編成注記
- DESIGN.md : ファイル構成セクションを新構造に更新
- ARCHITECTURE.md : 軽微な注記追加（任意）

### 5. 未対応 / 今後の推奨
- `phase_transition_observer/` の2ファイル（サイズ極小）は内容確認・修正 or experiments/legacy/ へ移動を推奨
- `grid_space_observer/`、`phase_shift_observer/` は当面ルートに残す（次フェーズで `observers/` 統合検討可）
- 必要に応じて `pyproject.toml` や `setup.py` でパッケージ化（将来的）
- 各実験ファイルのREADME追記や、テストの統一

## 新しい推奨ディレクトリ構造
```
hubCUBE/
├── README.md
├── ARCHITECTURE.md
├── DESIGN.md
├── REORGANIZATION_LOG.md   ← 本ファイル
├── docs/
│   ├── constraints.md
│   ├── dynamics.md
│   ├── forces.md
├── forces/
│   ├── __init__.py
│   └── CarryForce_v4.py
├── templates/
│   ├── __init__.py
│   └── hubCUBE_SingleRole_Template_v4_ForceBased.py
├── experiments/
│   ├── __init__.py
│   ├── CUBE_Anomaly_Detection_*.py (v2.6〜2.8)
│   ├── CarryField_v3_Minimal.py
│   ├── hubCUBE_SingleRole_Template*.py (旧版)
│   └── SimpleDynamicsSolver_example.py
├── grid_space_observer/
├── phase_shift_observer/
└── phase_transition_observer/   (要確認)
```

## 影響と注意
- ルートから直接 `python hubCUBE_SingleRole_Template_v4_ForceBased.py` は動作しなくなりました。代わりに `python -m templates.hubCUBE_SingleRole_Template_v4_ForceBased` または PYTHONPATH=. で実行してください。
- 主要なv4系は正しく動作するようimportを修正済み。
- Git履歴は保持されています（移動は新しいコミットとして記録）。

**実験は忠実に実際行って。** この整理により、モジュール性と可読性が向上し、今後のForce追加（RepairForce等）が容易になります。

---
**次のステップ推奨**:
1. phase_transition_observer の詳細チェックと修正
2. 下層 observer pyファイルのコードレビュー
3. 必要に応じて examples/ や tests/ の追加整備

ご質問・修正指示があればお知らせください。