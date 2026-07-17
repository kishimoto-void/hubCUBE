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
    """
    position: np.ndarray
    velocity: np.ndarray
    acceleration: np.ndarray = field(default_factory=lambda: np.zeros(3))

    def __post_init__(self):
        self.position = np.asarray(self.position, dtype=np.float64)
        self.velocity = np.asarray(self.velocity, dtype=np.float64)
        self.acceleration = np.asarray(self.acceleration, dtype=np.float64)

    def validate(self) -> Tuple[bool, str]:
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
    last_delta: np.ndarray = field(default_factory=lambda: np.zeros(3))
    momentum: np.ndarray = field(default_factory=lambda: np.zeros(3))
    payload: Dict[str, Any] = field(default_factory=dict)

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
    派生メトリクス（純結に計算・再計算される値）

    重要:
    - これらは状態そのものではなく、観測・計算される派生値である
    - recompute()を使って純結に再計算することを推奨
    """
    energy: float = 100.0
    entropy: float = 0.0
    stability: float = 1.0
    oscillation: float = 0.0
    residue_norm: float = 0.0
    velocity_norm: float = 0.0

    def update_derived_cache(self, field_state: PhysicsField):
        """ パフォーマンス上のキャッシュ更新（少ない項目のみ） """
        self.velocity_norm = float(np.linalg.norm(field_state.velocity))

    def recompute(
        self,
        field: PhysicsField,
        violations: Optional[list] = None,
        residue_norm: Optional[float] = None
    ):
        """
        派生メトリクスを純結に再計算する。

        これが Evaluation の主な入力インターフェースになる予定。
        """
        # velocity_norm
        self.velocity_norm = float(np.linalg.norm(field.velocity))

        # residue_norm
        if residue_norm is not None:
            self.residue_norm = float(residue_norm)
        elif violations:
            self.residue_norm = float(len(violations)) * 0.8
        else:
            self.residue_norm = 0.0

        # stability: 純結な派生計算
        v = self.velocity_norm
        r = self.residue_norm
        v_count = len(violations) if violations else 0
        self.stability = max(0.0, min(1.0, 1.0 / (1.0 + v * 0.04 + r * 0.12 + v_count * 0.25)))

        # entropy / oscillation は現在はダミー（後続で拡張）
        # self.entropy = ...
        # self.oscillation = ...

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
    step: int
    time: float
    position: np.ndarray
    velocity: np.ndarray
    status: str


@dataclass
class History:
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
    step: int = 0
    time: float = 0.0
    status: str = "stable"
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
    field: PhysicsField
    carry: Carry = field(default_factory=Carry)
    metrics: Metrics = field(default_factory=Metrics)
    metadata: Metadata = field(default_factory=Metadata)
    history: Optional[History] = None

    def __post_init__(self):
        self.metrics.update_derived_cache(self.field)

    def validate(self) -> Tuple[bool, str]:
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
        from constraints.ConstraintCore import ConstraintInput
        return ConstraintInput(
            position=self.field.position.copy(),
            velocity=self.field.velocity.copy(),
            energy=self.metrics.energy,
            carry_direction=self.carry.last_delta.copy()
        )

    def to_dict(self) -> Dict[str, Any]:
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
