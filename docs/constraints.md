# Constraints

## 役割

Constraint Modules は「状態が取り得る範囲や構造」を定義する拘束条件です。

Constraints は力を生み出しません。可能な運動を制限するだけです。

## 主な Constraint

- `GeometryConstraint`：位置関係・位相構造・幾何学的整合性
- `BoundaryConstraint`：residue やエネルギーの上限・下限
- `TopologyConstraint`：リンク構造や接続関係の制約

## 設計原則

- Constraint は状態を更新しない
- Constraint は「許容範囲」や「構造的制約」を返す
- Dynamics Solver が Force と Constraint を組み合わせて最終状態を決定する
- Geometry は Force ではなく Constraint である（ARCHITECTURE.md 参照）
