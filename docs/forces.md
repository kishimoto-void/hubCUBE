# Forces

## 役割

Force Modules は「状態をどの方向にどれだけ変化させるか」を計算する純粋な力生成器です。

Force は状態を直接更新しません。Dynamics Solver が複数の Force を合成した後に状態が更新されます。

## 現在の実装

- `CarryForce`（`CarryForce_v4.py`）
  - 過去の residue を次のステップへ運ぶ力
  - `compute_force(old_residue, persistence)` のみ返す

## 将来的に追加予定の Force

- `BubbleForce`：局所的な「泡（仮説の塊）」を形成・維持する力
- `RepairForce`：residue や構造の破損を修復する力
- `MomentumForce`：慣性・速度を考慮した力
- `NoiseForce`：探索・多様性を生むノイズ力
- `GravityForce`：特定の attractor への引力

## 設計原則

- Force は状態を持たない（または最小限）
- Force は「力のベクトル」を返すだけ
- 複数の Force をベクトル和で合成する
- 新しい Force を追加する際は、ARCHITECTURE.md の原則に従う
