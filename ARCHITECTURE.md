# hubCUBE Architecture Vision

## Purpose

hubCUBE is not a framework for controlling an LLM.

Its objective is to build a **phase dynamics engine** that observes, propagates, and repairs information as a physical process.

The LLM is treated as only one computational component inside this system.

**The engine itself owns the state.**

## Design Philosophy

Traditional agent architectures often look like:

```
Input
 ↓
LLM
 ↓
Output
```

hubCUBE intentionally inverts this relationship.

```
Reality
 ↓
Observation
 ↓
Phase Space
 ↓
Dynamics
 ↓
LLM
 ↓
Reality
```

The LLM never owns the global state.
Instead, it only expands one local hypothesis at a time.

## Core Principles

### 1. State exists outside the LLM

The digital state is always stored inside hubCUBE.

Examples:
- Phase
- Residue
- Geometry
- Tension
- Confidence
- Waypoints
- Bubble states

The LLM receives only a structured packet describing the current local state.

### 2. Observation and Evaluation are different

Observation never makes decisions.
It only measures.

Example observations:
- distance
- energy
- entropy
- residue
- trajectory
- links

Evaluation determines meaning:
- danger
- importance
- repair priority
- advance possibility

Keeping these separated prevents hidden reasoning from leaking into sensors.

### 3. Dynamics owns transitions

State transitions are never directly performed by the LLM.
Transitions emerge from dynamics.

```
Force
+
Constraints
↓
Dynamics Solver
↓
New State
```

### 4. Carry is not Dynamics

Carry only propagates previous information.

- Carry never decides.
- Carry never repairs.
- Carry never evaluates.
- Carry only transports information across time.

### 5. Every subsystem contributes forces

Subsystems do not modify the world directly.
Instead they produce forces.

Examples:
- CarryForce
- BubbleForce
- RepairForce
- NoiseForce
- GravityForce

Dynamics Solver integrates them.

### 6. Constraints never create motion

Geometry is not a force.
Boundary is not a force.
Topology is not a force.
They constrain possible motion.

```
Forces
↓
Constraints
↓
Integrated State
```

## Target Architecture

```
Reality
      ↓
Sensors
      ↓
Observation Layer
      ↓
Interpreter
      ↓
Phase State
      ↓
Force Modules
      ↓
      ├─── CarryForce
      ├─── BubbleForce
      ├─── RepairForce
      ├─── NoiseForce
      ├─── GravityForce
      ↓
Constraint Modules
      ↓
      ├─── GeometryConstraint
      ├─── BoundaryConstraint
      ├─── TopologyConstraint
      ↓
Dynamics Solver
      ↓
New Phase State
      ↓
Evaluation Layer
      ↓
Phase Packet
      ↓
LLM
```

## Repository Structure

```
hubCUBE/

├── observation/     # Pure measurement only.
├── state/           # Digital phase state.
├── dynamics/        # State integration.
├── forces/          # Independent force generators.
├── constraints/     # Geometry and boundary constraints.
├── evaluation/      # Risk and information evaluation.
├── carry/           # Information propagation only.
├── packet/          # Structured interface to external systems.
├── repair/          # Local recovery algorithms.
├── experiments/     # Experimental simulations.
```

## Long-term Goal

hubCUBE aims to become a **general-purpose phase dynamics engine**.

The system should not depend on a specific LLM.
Instead, any reasoning engine (LLM, symbolic system, planner, simulator, etc.) can interact through the same structured interface.

The ultimate objective is to represent information flow, uncertainty, repair, and adaptation as dynamical processes in a shared phase space, rather than embedding those responsibilities inside a single model.

## Design Rules

When adding new functionality, follow these principles:

- **Sensors** measure; they do not judge.
- **Observations** describe; they do not interpret.
- **Forces** influence; they do not update state directly.
- **Constraints** restrict motion; they do not generate it.
- Only the **Dynamics Solver** updates the Phase State.
- **Evaluation** analyzes the resulting state but does not modify it.
- External reasoning systems (including LLMs) operate only through **PhasePacket** and never own the global state.

---

*This document serves as the canonical architecture reference for both human developers and LLM-assisted development.*