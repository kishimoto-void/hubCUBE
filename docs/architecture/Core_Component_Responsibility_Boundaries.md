# hubCUBE コアコンポーネント責務境界設計

**作成日**: 2026-07-17
**目的**: DynamicsSolver, Force, Constraint, State の知識境界を明確に定義し、長期的に拡張可能なアーキテクチャを確立する。
**位置づけ**: ARCHITECTURE.md および DESIGN.md の設計思想を、具体的なコンポーネントレベルで具現化するための境界定義文書。

---

## 1. 基本原則

hubCUBE の最大の価値は「**力学のモジュール化**」にある。

そのために、以下の原則を最優先で守る：

- **知識の最小化**: 各コンポーネントは、自身の役割を果たすために必要な最小限の情報しか持たない。
- **更新の単一責任**: 状態を更新できるのは **DynamicsSolver（Integrator）のみ**。
- **Force は「意図」だけを表現**: Force は「こうありたい」という力や変化の要求を返す。状態の更新方法を知らない。
- **Constraint は「制約」だけを表現**: Constraint は状態が許容される範囲や修正を返す。状態を直接更新しない。
- **Solver は「実行」だけを担当**: Solver は Force と Constraint の結果を基に状態遷移を実行する。物理法則や特定の状態の意味を知らない。

---

## 2. 各コンポーネントの責務と知識境界

### 2.1 DynamicsSolver（Integrator）

**役割**: 状態遷移の実行（唯一の状態更新担当）

**知っていてよいこと**:
- 現在の状態（抽象的な State インターフェース経由）
- Force から提供される変化要求（ForceVector など）
- Constraint から提供される判断・修正（ConstraintDecision や Projection など）
- 状態遷移を実行するための最小限の機構（例: 加算、積分など）

**知っていてはいけないこと / してはいけないこと**:
- 特定の状態フィールドの意味（`residue`, `position`, `energy` などの意味）
- 状態の物理的・意味的な更新ロジック（velocity = ..., energy = ... など）
- `clamp` などの具体的な制約処理（これは BoundaryConstraint の責務）
- `step` の管理（Simulation / World / Clock の責務）
- `history` の管理（Recorder / HistoryManager の責務）
- 特定の Force や Constraint の実装詳細

**理想的な姿**:
Solver は「ΔState を適用する純粋な実行層」として振る舞う。
将来的には `state.apply_delta(...)` のような抽象インターフェースを通じて状態を更新する形が望ましい。

---

## 2.2 Force（ForceVector を含む）

**役割**: 「状態に対してどのような変化を望むか」を表現する

**知っていてよいこと**:
- 自身が作用したい対象（target）の識別子
- 作用の強さ・方向（value）
- 優先度や発生源などの付加情報

**知っていてはいけないこと / してはいけないこと**:
- 状態の具体的な更新方法
- 他の Force との合成方法（Solver の責務）
- Constraint がどのように判断するかの詳細

**推奨表現**:
生の `torch.Tensor` ではなく、`ForceVector` のような構造化されたオブジェクトを使う。
将来的には `target` を文字列ではなく、型安全な `StateField` Enum などで表現することが望ましい。

---

## 2.3 Constraint

**役割**: 状態が取りうる範囲や、望ましい修正を定義する

**知っていてよいこと**:
- 現在の状態（または状態の一部）
- 許容範囲や射影（Projection）の定義

**知っていてはいけないこと / してはいけないこと**:
- 状態を直接更新すること
- 「この状態にしなさい」と具体的な次の状態を返すこと
- 特定の Force の意図を解釈すること

**推奨表現**:
単なる `allow/scale` ではなく、以下のようなより表現力の高い形式を検討する：
- `Projection`（状態を許容領域に射影した結果を返す）
- `Correction`（必要な修正量を返す）
- `ConstraintDecision`（allow, scale, reject_reason など）

Constraint は「判定器」ではなく「制約の定義」として振る舞う。

---

## 2.4 PhaseState（および State 全般）

**役割**: 現在のシステムの状態を保持する

**知っていてよいこと**:
- 自身のフィールド値
- 最小限のメタ情報（必要に応じて）

**知っていてはいけないこと / してはいけないこと**:
- 自身の更新ロジック（Solver に委譲）
- 歴史の管理（history は極力 State から分離し、Recorder に委譲）
- 無制限の `metadata` 辞書（神クラス化の温床になるため、用途を厳しく制限するか廃止を検討）

**推奨**:
PhaseState は「動的状態のスナップショット」として最小限に保つ。
`history` や過度な `metadata` は State の外に置く。
将来的には異なるドメイン（MemoryState, TopologyState など）に対応できる汎用的な State インターフェースを検討する。

---

## 3. 推奨する抽象化の方向性

### 3.1 ForceVector（推奨）
```python
@dataclass
class ForceVector:
    target: str | StateField   # 将来的には StateField Enum
    value: Any
    priority: float = 1.0
    source: str = "unknown"
    mode: str = "add"          # add, replace, subtract など
```

### 3.2 ConstraintDecision / Projection（推奨）
Constraint は単なる bool/scale ではなく、以下のような形式を検討：
- `Projection`: 状態を制約を満たす領域に写像した結果を返す
- `Correction`: 必要な修正ベクトルを返す

### 3.3 SolverResult の拡張
将来的には以下を含める：
- `new_state`
- `applied_forces: List[ForceVector]`
- `constraint_decisions: List[...]`
- `diagnostics / events / warnings`
- `timing`

---

## 4. 現在の実装に対する評価と改善の方向

現在の `MinimalDynamicsSolver`（v3）は、Phase 1 の実験コードとしては一定の水準に達している。
しかし「hubCUBE の心臓部」として長期的に育てるには、以下の点が依然として問題である：

- Solver が `residue` や `PhaseState` の構造を直接知っている
- `clamp` が Solver にある（BoundaryConstraint の責務）
- `step` 更新が Solver にある
- `ForceVector.target` が文字列で型安全でない
- Constraint がまだ状態を直接見る形が強い

これらを解消するためには、**「Solver が知らない状態」で動かせる最小形**を次に目指すべきである。

---

## 5. 次に取るべきアクション（提案）

1. この文書を基に、関係者で責務境界を合意する
2. 合意した境界に基づいて `MinimalDynamicsSolver` を再設計する
3. `ForceVector` と Constraint のインターフェースをこの境界に沿って定義する
4. `PhaseState` から `history` を分離する方向を検討

---

## 6. 関連文書

- `ARCHITECTURE.md`
- `DESIGN.md`
- `ROADMAP.md`

---

**この文書は「完璧な最終形」を定義するものではなく、**「ここから先は知らない」という境界を明確にするための出発点**である。**

境界が固まれば、その後の Force Library や Constraint Library の追加は、はるかに安全かつ自然に行えるようになる。