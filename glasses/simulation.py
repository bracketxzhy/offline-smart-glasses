"""Measured sequential pipeline model; missing support/energy is never zero."""
import math


def simulate(workload: dict, paths: dict):
    if not workload or any(not math.isfinite(v) or v < 0 for v in workload.values()) or not math.isclose(sum(workload.values()), 1., abs_tol=1e-6):
        raise ValueError("Workload probabilities must be finite, nonnegative and sum to one")
    coverage, weighted_latency, weighted_energy = 0., 0., 0.
    energy_complete = True
    for query_type, probability in workload.items():
        if query_type not in paths:
            raise ValueError(f"Missing path declaration: {query_type}")
        path = paths[query_type]
        if path is None:
            continue
        stages = path["stages_ms"]
        if not stages or any(not math.isfinite(v) or v < 0 for v in stages.values()):
            raise ValueError("Stages must contain finite, nonnegative measured milliseconds")
        coverage += probability
        weighted_latency += probability * sum(stages.values())
        energy = path.get("energy_j")
        if energy is None:
            energy_complete = False
        elif not math.isfinite(energy) or energy < 0:
            raise ValueError("Energy must be finite and nonnegative")
        else:
            weighted_energy += probability * energy
    complete = math.isclose(coverage, 1., abs_tol=1e-6)
    return {"coverage": coverage, "expected_latency_ms": weighted_latency if complete else None, "latency_given_supported_ms": weighted_latency/coverage if coverage else None, "expected_energy_j": weighted_energy if complete and energy_complete else None}
