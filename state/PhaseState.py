from __future__ import annotations

from dataclasses import dataclass, field
import numpy as np
from typing import List, Dict, Any, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from constraints.ConstraintCore import ConstraintInput


@dataclass
class PhysicsField:
    """
    [物理状態フィールド]
    連続空間における力学ベクトル群。
    将来的に orientation, angular_velocity, mass などの拡張スロットを受け入れる。
    """
    position: np.ndarray      # 3次元座標 [x, y, z]
    velocity: np.ndarray      # 3次元速度ベクトル [vx, vy, vz]
    acceleration: np.ndarray = field(default_factory=lambda: np.zeros(3))  # 3次元加速度 [ax, ay, az]

    def __post_init__(self):
        self.position = np.asarray(self.position, dtype=np.float64)
        self.velocity = np.asarray(self.velocity, dtype=np.float64)
        self.acceleration = np.asarray(self.acceleration, dtype=np.float64)

    def validate(self) -> Tuple[bool, str]:
        """ 物理ベクトルの健全性を検証する """
        for name, arr in [("position", self.position), ("velocity", self.velocity), ("acceleration", self.acceleration)]:
            if arr.shape != (3,):
                return False, f"PhysicsField.{name} must have shape (3,), got {arr.shape}"
            if np.any(np.isnan(arr)):
                return False, f"PhysicsField.{name} contains NaN"
            if np.any(np.isinf(arr)):
                return False, f"PhysicsField.{name} contains Infinity"
        return True, "OK"


@dataclass
class Carry:
    """
    [慫性情報フィールド]
    シミュレーションのステップ間を「持ち運ぶ（Carry）」ための一時特性。
    """
    last_delta: np.ndarray = field(default_factory=lambda: np.zeros(3))  # 前回ステップの確定移動変位
    momentum: np.ndarray = field(default_factory=lambda: np.zeros(3))    # 積積された慫性・モーメンタム
    payload: Dict[str, Any] = field(default_factory=dict)               # 記憶ではなく「持ち運ぶペイロード」

    def __post_init__(self):
        self.last_delta = np.asarray(self.last_delta, dtype=np.float64)
        self.momentum = np.asarray(self.momentum, dtype=np.float64)

    def validate(self) -> Tuple[bool, str]:
        for name, arr in [("last_delta", self.last_delta), ("momentum", self.momentum)]:
            if arr.shape != (3,):
                return False, f"Carry.{name} must have shape (3,), got {arr.shape}"
            if np.any(np.isnan(arr)):
                return False, f"Carry.{name} contains NaN"
            if np.any(np.isinf(arr)):
                return False, f"Carry.{name} contains Infinity"
        return True, "OK"


@dataclass
class Metrics:
    """
    [派生キャッシュ・フィールド]
    ※重要: このクラス内の全プロパティは状態そのものではなく、
    PhysicsField等から計算される『派生値（キャッシュ）』です。
    EvaluationやObserver、可視化層がO(1)で高速アクセスするために保持されます。

    update_derived_cache() は Solver / ConstraintPipeline 適用後に呼び出すこと。
    energy, stability, residue_norm などの更新責任は Evaluation層による。
    """
    energy: float = 100.0        # システムが活動可能な残りエネルギー
    entropy: float = 0.0         # 乱雑度・カオス指数
    stability: float = 1.0       # 挙動の安定度指標 (1.0: 安定, 0.0: 発散/崩壊)
    oscillation: float = 0.0     # 軌道の往復振動強度
    residue_norm: float = 0.0    # 積分・制約補正時の差分残差L2ノルム
    velocity_norm: float = 0.0   # 速度のL2絶対値（キャッシュ）

    def update_derived_cache(self, field_state: PhysicsField, *, residue_norm: Optional[float] = None):
        """
        PhysicsFieldの状態からキャッシュとなる統計量を同期更新する。

        Solverまたは ConstraintPipeline 適用後に呼び出すことを推奨。
        """
        self.velocity_norm = float(np.linalg.norm(field_state.velocity))
        if residue_norm is not None:
            self.residue_norm = float(residue_norm)

    def validate(self) -> Tuple[bool, str]:
        if self.energy < 0.0:
            return False, f"Metrics.energy cannot be negative: {self.energy}"
        for name, val in [
            ("energy", self.energy), ("entropy", self.entropy),
            ("stability", self.stability), ("oscillation", self.oscillation),
            ("residue_norm", self.residue_norm), ("velocity_norm", self.velocity_norm)
        ]:
            if np.isnan(val):
                return False, f"Metrics.{name} is NaN"
            if np.isinf(val):
                return False, f"Metrics.{name} is Infinity"
        return True, "OK"


@dataclass
class HistoryRecord:
    """[履歴レコード] 評価層（Evaluation）に渡す不変のタイムシークエンスログ"""
    step: int
    time: float
    position: np.ndarray
    velocity: np.ndarray
    status: str


@dataclass
class History:
    """[履歴管理バッファ] 大規模シミュレーションのメモリ最適化用コンテナ"""
    records: List[HistoryRecord] = field(default_factory=list)
    max_len: int = 1000

    def append(self, step: int, time_val: float, field_state: PhysicsField, status: str):
        if len(self.records) >= self.max_len:
            self.records.pop(0)
        self.records.append(
            HistoryRecord(
                step=step,
                time=time_val,
                position=field_state.position.copy(),
                velocity=field_state.velocity.copy(),
                status=status
            )
        )


@dataclass
class Metadata:
    """[制御・同期用メタデータ]"""
    step: int = 0
    time: float = 0.0
    status: str = "stable"       # "stable", "violated", "critical", "halted"
    custom_tags: List[str] = field(default_factory=list)
    attributes: Dict[str, Any] = field(default_factory=dict)

    def validate(self) -> Tuple[bool, str]:
        if self.step < 0:
            return False, f"Metadata.step cannot be negative: {self.step}"
        if self.time < 0.0 or np.isnan(self.time) or np.isinf(self.time):
            return False, f"Metadata.time is invalid: {self.time}"
        return True, "OK"


@dataclass
class PhaseState:
    """
    [hubCUBE 共通コア状態モデル]
    システム内のあらゆる状態（物理、慫性、特性、メタ）を1つに集約する唯一の状態構造。
    各サブレイヤーが不要な情報に一切依存しない極限のデカップリングを実現。
    """
    field: PhysicsField
    carry: Carry = field(default_factory=Carry)
    metrics: Metrics = field(default_factory=Metrics)
    metadata: Metadata = field(default_factory=Metadata)
    # 大量エージェント実行時の超軽量化のため、Historyは完全Optional化
    history: Optional[History] = None

    def __post_init__(self):
        self.metrics.update_derived_cache(self.field)

    def validate(self) -> Tuple[bool, str]:
        """
        [改善点①: シミュレーションの品質アサーション]
        Solver積分後や各ステップ終了時に「数値崩壊（NaN/Inf/不正形状/負値）」を検関する。
        """
        for section, validator in [
            ("field", self.field.validate),
            ("carry", self.carry.validate),
            ("metrics", self.metrics.validate),
            ("metadata", self.metadata.validate)
        ]:
            success, error_msg = validator()
            if not success:
                return False, f"State Validation Failed at [{section}] -> {error_msg}"
        return True, "OK"

    def to_constraint_input(self) -> "ConstraintInput":
        """
        ConstraintPipelineで使用する ConstraintInput への変換。
        constraints/ レイヤーとの結合を滑らかにするためのブリッジメソッド。
        """
        # 循環インポート回避のために後方インポート
        from constraints.ConstraintCore import ConstraintInput
        return ConstraintInput(
            position=self.field.position.copy(),
            velocity=self.field.velocity.copy(),
            energy=self.metrics.energy,
            carry_direction=self.carry.last_delta.copy()
        )

    def to_dict(self) -> Dict[str, Any]:
        """DB保存やファイル永続化用の完全なシリアライズデータ"""
        data = {
            "field": {
                "position": self.field.position.tolist(),
                "velocity": self.field.velocity.tolist(),
                "acceleration": self.field.acceleration.tolist(),
            },
            "carry": {
                "last_delta": self.carry.last_delta.tolist(),
                "momentum": self.carry.momentum.tolist(),
                "payload": self.carry.payload.copy(),
            },
            "metrics": {
                "energy": self.metrics.energy,
                "entropy": self.metrics.entropy,
                "stability": self.metrics.stability,
                "oscillation": self.metrics.oscillation,
                "residue_norm": self.metrics.residue_norm,
                "velocity_norm": self.metrics.velocity_norm,
            },
            "metadata": {
                "step": self.metadata.step,
                "time": self.metadata.time,
                "status": self.metadata.status,
                "custom_tags": list(self.metadata.custom_tags),
                "attributes": self.metadata.attributes.copy(),
            }
        }
        if self.history is not None:
            data["history"] = [
                {
                    "step": r.step,
                    "time": r.time,
                    "position": r.position.tolist(),
                    "velocity": r.velocity.tolist(),
                    "status": r.status
                } for r in self.history.records
            ]
        return data

    def to_packet(self) -> Dict[str, Any]:
        """
        [改善点④: LLM(Packet)・軽量パケット通信用のサブセット出力]
        LLMのコンテキストウィンドウを汚さず、要点だけを渡すための超軽量セグメント。
        """
        return {
            "id": self.metadata.attributes.get("agent_id", "hubcube_node"),
            "step": self.metadata.step,
            "status": self.metadata.status,
            "pos": [round(float(x), 4) for x in self.field.position],
            "vel": [round(float(x), 4) for x in self.field.velocity],
            "energy": round(self.metrics.energy, 2),
            "stability": round(self.metrics.stability, 3),
            "tags": self.metadata.custom_tags
        }

    def clone(self) -> "PhaseState":
        """NumPy配列およびメタ情報のディープコピーを最速で生成する複製機構"""
        cloned_history = None
        if self.history is not None:
            cloned_history = History(
                records=[
                    HistoryRecord(
                        step=r.step,
                        time=r.time,
                        position=r.position.copy(),
                        velocity=r.velocity.copy(),
                        status=r.status
                    ) for r in self.history.records
                ],
                max_len=self.history.max_len
            )

        return PhaseState(
            field=PhysicsField(
                position=self.field.position.copy(),
                velocity=self.field.velocity.copy(),
                acceleration=self.field.acceleration.copy()
            ),
            carry=Carry(
                last_delta=self.carry.last_delta.copy(),
                momentum=self.carry.momentum.copy(),
                payload=self.carry.payload.copy()
            ),
            metrics=Metrics(
                energy=self.metrics.energy,
                entropy=self.metrics.entropy,
                stability=self.metrics.stability,
                oscillation=self.metrics.oscillation,
                residue_norm=self.metrics.residue_norm,
                velocity_norm=self.metrics.velocity_norm
            ),
            metadata=Metadata(
                step=self.metadata.step,
                time=self.metadata.time,
                status=self.metadata.status,
                custom_tags=list(self.metadata.custom_tags),
                attributes=self.metadata.attributes.copy()
            ),
            history=cloned_history
        )
