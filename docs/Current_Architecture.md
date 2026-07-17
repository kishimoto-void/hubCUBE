# hubCUBE 現在のアーキテクチャ概要（2026-07-17時点）

**作成日**: 2026-07-17
**目的**: 再編成後および責務境界設計後の hubCUBE の実際の構造と設計思想をまとめる。

---

## 1. 全体像

hubCUBE は「**状態遷移を力学的にモジュール化する**」ことを目的とした Phase Dynamics Engine です。

基本的な流れ（理想形）:

```
State
  ↓
Force Library（CarryForce, BubbleForce, RepairForce...）
  ↓
Constraint Library（BoundaryConstraint, GeometryConstraint...）
  ↓
DynamicsSolver（Integrator）
  ↓
New State
  ↓
PhasePacket（LLMへのインターフェース）
```

LLM はグローバルな状態を持たず、**PhasePacket** のみを受け取って推論を行う。
状態の更新はすべて **DynamicsSolver** が担う。

---

## 2. 現在のディレクトリ構造（2026-07-17 再編成後）

```
hubCUBE/
├── README.md
├── ARCHITECTURE.md          # 長期ビジョン
├── DESIGN.md                  # 設計原則
├── ROADMAP.md                 # 実験ロードマップ
├── REORGANIZATION_LOG.md      # 再編成記録
├── docs/
│   ├── architecture/
│   │   └── Core_Component_Responsibility_Boundaries.md  # 責務境界定義
│   └── Current_Architecture.md  # 本ファイル
├── forces/
│   ├── __init__.py
│   └── CarryForce_v4.py
├── templates/
│   ├── __init__.py
│   └── hubCUBE_SingleRole_Template_v4_ForceBased.py
├── dynamics/
│   ├── __init__.py
│   └── MinimalDynamicsSolver.py   # Phase 1 実装（v4）
├── experiments/
│   ├── __init__.py
│   ├── SimpleDynamicsSolver_example.py
│   ├── CarryField_v3_Minimal.py
│   └── ...（レガシー実験コード）
├── grid_space_observer/
├── phase_shift_observer/
└── phase_transition_observer/
```

---

## 3. コアコンポーネントの現状

### 3.1 Force
- `forces/CarryForce_v4.py`：純粋な Force Generator（状態更新をしない）
- `ForceVector` を導入（target, value, priority, mode, source）
- 今後: BubbleForce, RepairForce, MomentumForce などを追加予定

### 3.2 Constraint
- まだ本格実装なし（Phase 1）
- `ConstraintDecision` を定義済み
- 将来的に BoundaryConstraint, GeometryConstraint を `constraints/` に配置

### 3.3 DynamicsSolver（Integrator）
- `dynamics/MinimalDynamicsSolver.py`（v4）
- 責務を「状態遷移の実行」に限定する方向で再設計済み
- ForceVector と ConstraintDecision を受け取る形
- まだ一部の責務（clamp など）が残っているが、コメントで方向性を明記

### 3.4 State
- `PhaseState`（dynamics/ 内に定義）
- position, velocity, energy, residue, carry などを保持
- history は PhaseState から分離する方向を検討中

### 3.5 Template
- `templates/hubCUBE_SingleRole_Template_v4_ForceBased.py`
- CarryForce を使用した実用例
- 将来的に MinimalDynamicsSolver を利用する形へ移行予定

---

## 4. 現在の設計原則（2026-07-17 更新版）

1. **Solverだけが状態を更新する**
2. **Force は「意図」だけを返す**（状態更新をしない）
3. **Constraint は「制約」だけを表現**（状態を直接更新しない）
4. **各コンポーネントの知識を最小化する**（責務境界を明確に）
5. **PhasePacket を介してのみ LLM と接続する**

詳細は `docs/architecture/Core_Component_Responsibility_Boundaries.md` を参照。

---

## 5. 主要な設計文書

| 文書 | 内容 | 状態 |
|------|------|------|
| ARCHITECTURE.md | 長期ビジョンと全体構造 | 安定 |
| DESIGN.md | 詳細な設計原則 | 安定 |
| ROADMAP.md | 実験優先順位 | 2026-07-17 改訂済み |
| Core_Component_Responsibility_Boundaries.md | 各コンポーネントの知識境界 | 2026-07-17 新規作成 |
| Current_Architecture.md | 本ファイル（実装状況まとめ） | 2026-07-17 新規作成 |

---

## 6. 現在の課題と次の優先事項

### 残っている主な課題
- DynamicsSolver がまだ一部の具体的な状態（residue）を直接扱っている
- Constraint 層が未実装
- Boundary 処理（clamp）が Solver 内に残っている
- PhaseState に history が混在しやすい

### 次の優先事項（推奨順）
1. Constraint 層の最小実装（特に BoundaryConstraint）
2. DynamicsSolver のさらなる薄型化（責務境界に沿った再設計）
3. ForceVector の複数ターゲット対応
4. PhaseState から history の分離

---

## 7. 関連リンク

- [ARCHITECTURE.md](../ARCHITECTURE.md)
- [DESIGN.md](../DESIGN.md)
- [ROADMAP.md](../ROADMAP.md)
- [Core_Component_Responsibility_Boundaries.md](architecture/Core_Component_Responsibility_Boundaries.md)

---

**この文書は「現在の実装状況」を記録するものであり、理想形ではありません。**

設計は `Core_Component_Responsibility_Boundaries.md` を基に継続的に改善中です。