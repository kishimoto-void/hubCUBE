# hubCUBE 現在のアーキテクチャ概要（2026-07-17時点）

**作成日**: 2026-07-17
**目的**: 再編成後および MinimalDynamicsSolver v4 実装時点での、hubCUBE の現在のアーキテクチャと設計思想を整理する。

---

## 1. 全体像

hubCUBE は「**力学のモジュール化**」を最大の価値とする Phase Dynamics Engine である。

基本的な流れは以下の通り：

```
State
  ↓
Force Library（CarryForce など）
  ↓
Constraint Library（将来的に）
  ↓
DynamicsSolver（Integrator）
  ↓
New State
```

LLM はグローバルな状態を持たず、`PhasePacket` を通じてのみ hubCUBE とやり取りする設計を目指している。

---

## 2. 現在のディレクトリ構造

```
hubCUBE/
├── README.md
├── ARCHITECTURE.md（理想形）
├── DESIGN.md
├── ROADMAP.md
├── REORGANIZATION_LOG.md
├── docs/
│   └── architecture/
│       ├── Current_Architecture.md（本ファイル）
│       └── Core_Component_Responsibility_Boundaries.md
├── forces/
│   ├── CarryForce_v4.py
│   └── __init__.py
├── templates/
│   ├── hubCUBE_SingleRole_Template_v4_ForceBased.py
│   └── __init__.py
├── dynamics/
│   ├── MinimalDynamicsSolver.py（v4）
│   └── __init__.py
├── experiments/
│   └── （レガシーコード群）
├── grid_space_observer/
├── phase_shift_observer/
└── phase_transition_observer/
```

---

## 3. コアコンポーネントと現在の責務

### 3.1 Force（forces/）

**現在の実装**: `CarryForce_v4.py`

**責務**:
- 状態に対して「どのような変化を望むか」を表現する
- 現在は `ForceVector` を使用して `target` と `value` を明示

**現状の特徴**:
- 純粋な Force Generator として設計されており、状態更新は行わない
- 将来的に BubbleForce, RepairForce, MomentumForce などを追加予定

### 3.2 DynamicsSolver（dynamics/）

**現在の実装**: `MinimalDynamicsSolver.py`（v4）

**責務**:
- ForceVector と ConstraintDecision を受け取り、状態遷移を実行する（唯一の更新担当）
- 特定の状態フィールドの意味を極力知らない設計を目指している

**v4 の特徴**:
- `ForceVector` を正式に採用
- `ConstraintDecision` を導入
- メソッドを分割し、責務を明確化
- まだ `residue` ターゲットに特化した処理が残っている（改善余地あり）

### 3.3 Constraint（未実装）

現在はまだ独立したモジュールとして存在しない。
`MinimalDynamicsSolver` 内に一時的な `clamp` が残っている状態。

将来的には `BoundaryConstraint`, `GeometryConstraint` などを `constraints/` に配置予定。

### 3.4 State（PhaseState）

現在は `MinimalDynamicsSolver.py` 内に定義されている簡易版。

将来的には `state/PhaseState.py` への移行と、より汎用的なインターフェースの検討が必要。

---

## 4. 設計原則（2026-07-17時点の合意）

`docs/architecture/Core_Component_Responsibility_Boundaries.md` で定義された原則を採用している：

- **Solver は実行に徹する**：状態の意味や物理法則を知らない
- **Force は意図だけを返す**：`ForceVector` で target と value を明示
- **Constraint は判断を返す**：状態を直接更新しない
- **更新の単一責任**：状態を更新できるのは DynamicsSolver のみ

---

## 5. 現在の状況まとめ

| コンポーネント | 状況 | コメント |
|---------------|------|----------|
| Force | CarryForce_v4 が安定 | BubbleForce など追加予定 |
| DynamicsSolver | v4 で責務分離を強化 | まだ residue 依存が残る |
| Constraint | 未実装 | clamp が Solver に残っている |
| PhaseState | 簡易版が Solver 内に存在 | 汎用化が必要 |
| Observer | 独立ディレクトリで存在 | 将来的に ObservationForce 化を検討 |
| レガシーコード | experiments/ に一部移動済み | ルートにまだ残っているファイルあり |

---

## 6. 今後の主な方向性

- Constraint 層の本格実装（BoundaryConstraint, GeometryConstraint）
- ForceVector の複数ターゲット対応
- PhaseState の汎用化と history の分離
- PhasePacket の定義
- 複数 Role 間での力の相互作用実験

詳細は `ROADMAP.md` を参照。

---

**この文書は「現在の状態」をスナップショットとして記録するものであり、理想形（ARCHITECTURE.md）とは異なる場合がある。**