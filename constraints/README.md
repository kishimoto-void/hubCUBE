# constraints ディレクトリ

hubCUBE の Constraint Layer コアコンポーネントを格納します。

## 主要クラス

- `GeometryConstraint`: 境界制約（不変Geometryアセットを参照）
- `VelocityConstraint`: 速度制約
- `ConstraintPipeline`: Constraintを優先度順に適用するパイプライン
- `ViolationCollector`: 違反情報をゼロアロケーション近く収集

## 設計原則

- Constraintは状態を持たない純結関数
- Forceが提案した delta のみを検査・修正
- Solverは正当化された delta のみを使って状態を更新
- 違反は Evaluation Layer で利用可能

## 使用例

```python
from constraints import (
    GeometryConstraint, VelocityConstraint,
    ConstraintPipeline, ViolationCollector,
    ConstraintInput, ConstraintContext, ConstraintConfig,
    SphereGeometry, ForceOutput
)

pipeline = ConstraintPipeline([
    GeometryConstraint(),
    VelocityConstraint(),
])

# ...
```