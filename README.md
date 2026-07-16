# hubCUBE

CUBE Hub and SingleRoleCUBE template collection for modular observation architecture

## 設計思想 (v3.0+)

**Carryの責務を厳格に最小化**

Carryは「過去を次へ運ぶ」だけを担当します。

```
R(t+1) = decay * R(t) + Δ
```

Adaptive Decay / Geometry / Momentum / Boundary / Anomaly / Links は
すべて外側の **Field** または **Observation** レイヤーに分離します。

これにより将来、BubbleForce・Repair・Waypoint・PhaseGraph などを
「力の項」としてベクトル合成しやすくなります。

R' = CarryField + GeometryField + MomentumField + BoundaryField + ExternalInput

## Modules

- `CarryField_v3_Minimal.py` **NEW (v3)** — **最小CarryField**
  - 責務: propagate(old_residue, delta) のみ
  - effective_decay / boundary_fn / extra_terms を外部から注入
  - compute_persistence: cosine similarity で「どれだけ情報が残ったか」を正しく測定
  - velocity / anomaly / links を一切知らない純粋な運び屋
- `hubCUBE_SingleRole_Template_v2.2_ImprovedCarry.py` — v2.2（参考用、carryがやや肥大化していた版）
- `hubCUBE_SingleRole_Template.py` / v2.1 — 基本テンプレート
- `CUBE_Anomaly_Detection_v*.py` — 異常検知実験群
- `phase_shift_observer/PhaseShiftObserverCUBE_v4_3.py` — 位相ズレ観測器
- `grid_space_observer/GridSpaceObserver_v4_2.py` — 時空間幾何観測器
- `phase_transition_observer/PhaseTransitionCUBE_v1.2_LinkDynamics.py` — リンク力学観測器

## Usage Example (CarryField v3)

```python
from CarryField_v3_Minimal import CarryField
import torch

carry = CarryField(default_decay=0.87)
old_res = torch.randn(6)
delta = torch.randn(6) * 0.3

# Fieldからeffective_decayを与える例
new_res = carry.propagate(
    old_res, delta,
    effective_decay=0.92,           # AdaptiveDecayFieldから
    # boundary_fn=some_boundary.limit,
    # extra_terms=momentum_term     # MomentumFieldから
)

persistence = carry.compute_persistence(old_res, new_res)
print(f"Persistence: {persistence:.4f}")
```

実験は忠実に実際行って。