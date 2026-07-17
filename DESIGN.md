# hubCUBE Design Document (v4+)

## 現在のアーキテクチャ原則

### 1. Force / Constraint 分離

- **Force Generator**（力を生成するモジュール）
  - CarryForce, BubbleForce, RepairForce, NoiseForce など
  - 状態を更新せず、**力のベクトル**のみを返す

- **Constraint**（拘束を生成するモジュール）
  - GeometryConstraint, BoundaryConstraint, TopologyConstraint など
  - 状態の許容範囲を定義

- **Dynamics Solver** が唯一、状態を更新する

### 2. Carry の責務（v4）

CarryForce は「過去のresidueをどれだけ次のステップに運ぶか」という**力**だけを担当。

```python
carry_force = old_residue * persistence
```

状態更新・velocity計算・anomaly判定などは一切行わない。

### 3. PhaseState の考え方

Residue は独立した「状態」ではなく、PhaseState の一要素（residual vector）として扱うのが自然。

PhaseState の例:
- axis / position
- velocity
- residue (residual vector)
- energy / tension
- coherence, entropy など

### 4. 拡張性

新しい物理要素（Bubble, Repair, Waypoint, Gravity など）を追加する際は、
- 新しい Force Generator を追加
- Dynamics Solver で合成
するだけで済む。

## ファイル構成（2026-07-17 整理後）

**Core (最新推奨)**
- `forces/CarryForce_v4.py` : 純粋な Carry Force Generator
- `templates/hubCUBE_SingleRole_Template_v4_ForceBased.py` : CarryForce を実際に使ったテンプレート（最新推奨）

**Examples & Experiments**
- `experiments/SimpleDynamicsSolver_example.py` : Force合成の最小例
- `experiments/CUBE_Anomaly_Detection_v*.py` : Anomaly検出実験群（v2.6〜2.8）
- `experiments/CarryField_v3_Minimal.py` など過去バージョン（参考用）

**Documentation**
- `DESIGN.md`, `ARCHITECTURE.md`, `REORGANIZATION_LOG.md`
- `docs/` : constraints, dynamics, forces 関連の補足

**Observers** (当面ルート)
- `phase_shift_observer/`, `grid_space_observer/`, `phase_transition_observer/`

**過去バージョン（experiments/ に移動済み）**
- v2.2_ImprovedCarry, v3_CarryField など : 参考として experiments/ にアーカイブ

**Note**: 2026-07-17 にルートクリーンアップを実施。詳細は REORGANIZATION_LOG.md を参照。

実験は忠実に実際行って。