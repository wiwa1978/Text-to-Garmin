"""Convert workout models to Garmin Connect JSON format."""

from __future__ import annotations

from typing import Iterator

from text_to_garmin.models import (
    CooldownStep,
    DurationType,
    IntervalStep,
    RepeatStep,
    RestStep,
    RunStep,
    WarmupStep,
    Workout,
    WorkoutStep,
)

_SPORT_TYPE = {
    "sportTypeId": 1,
    "sportTypeKey": "running",
    "displayOrder": 1,
}

_STEP_TYPE_MAP: dict[str, dict] = {
    "warmup": {"stepTypeId": 1, "stepTypeKey": "warmup", "displayOrder": 1},
    "cooldown": {"stepTypeId": 2, "stepTypeKey": "cooldown", "displayOrder": 2},
    "run": {"stepTypeId": 3, "stepTypeKey": "interval", "displayOrder": 3},
    "interval": {"stepTypeId": 3, "stepTypeKey": "interval", "displayOrder": 3},
    "rest": {"stepTypeId": 4, "stepTypeKey": "recovery", "displayOrder": 4},
}

_END_CONDITION_MAP: dict[str, dict] = {
    "lap_button": {
        "conditionTypeId": 1,
        "conditionTypeKey": "lap.button",
        "displayOrder": 1,
        "displayable": True,
    },
    "time": {
        "conditionTypeId": 2,
        "conditionTypeKey": "time",
        "displayOrder": 2,
        "displayable": True,
    },
    "distance": {
        "conditionTypeId": 3,
        "conditionTypeKey": "distance",
        "displayOrder": 3,
        "displayable": True,
    },
}

_NO_TARGET = {
    "workoutTargetTypeId": 1,
    "workoutTargetTypeKey": "no.target",
    "displayOrder": 1,
}

_STROKE_TYPE = {"strokeTypeId": 0, "displayOrder": 0}
_EQUIPMENT_TYPE = {"equipmentTypeId": 0, "displayOrder": 0}


def _id_counter(start: int = 600_000_001) -> Iterator[int]:
    n = start
    while True:
        yield n
        n += 1


def _build_executable_step(
    step: WarmupStep | CooldownStep | RunStep | IntervalStep | RestStep,
    step_id: int,
    step_order: int,
) -> dict:
    end_cond_key = step.duration_type.value
    end_condition = dict(_END_CONDITION_MAP[end_cond_key])
    end_condition_value: float | None = None

    if step.duration_type != DurationType.LAP_BUTTON and step.duration is not None:
        end_condition_value = step.duration

    result: dict = {
        "type": "ExecutableStepDTO",
        "stepId": step_id,
        "stepOrder": step_order,
        "stepType": dict(_STEP_TYPE_MAP[step.type]),
        "endCondition": end_condition,
        "endConditionValue": end_condition_value,
        "targetType": dict(_NO_TARGET),
        "strokeType": dict(_STROKE_TYPE),
        "equipmentType": dict(_EQUIPMENT_TYPE),
    }
    return result


def _build_steps(
    steps: list[WorkoutStep],
    ids: Iterator[int],
    order_start: int,
) -> tuple[list[dict], int]:
    """Recursively build Garmin step dicts. Returns (steps_list, next_order)."""
    result: list[dict] = []
    order = order_start

    for step in steps:
        step_id = next(ids)

        if isinstance(step, RepeatStep):
            repeat_order = order
            order += 1
            child_steps, order = _build_steps(step.steps, ids, order)
            result.append({
                "type": "RepeatGroupDTO",
                "stepId": step_id,
                "stepOrder": repeat_order,
                "stepType": {
                    "stepTypeId": 6,
                    "stepTypeKey": "repeat",
                    "displayOrder": 6,
                },
                "numberOfIterations": step.count,
                "workoutSteps": child_steps,
                "endConditionValue": float(step.count),
                "endCondition": {
                    "conditionTypeId": 7,
                    "conditionTypeKey": "iterations",
                    "displayOrder": 7,
                    "displayable": False,
                },
                "smartRepeat": False,
            })
        else:
            result.append(_build_executable_step(step, step_id, order))
            order += 1

    return result, order


def build_garmin_workout(workout: Workout) -> dict:
    """Convert a Workout model into Garmin Connect JSON format."""
    ids = _id_counter()
    garmin_steps, _ = _build_steps(workout.steps, ids, order_start=1)

    return {
        "workoutName": workout.name,
        "description": "",
        "sportType": dict(_SPORT_TYPE),
        "workoutSegments": [
            {
                "segmentOrder": 1,
                "sportType": dict(_SPORT_TYPE),
                "workoutSteps": garmin_steps,
            }
        ],
    }


def workout_to_json_string(workout: Workout) -> str:
    """Convert a Workout to a pretty-printed Garmin JSON string."""
    import json

    return json.dumps(build_garmin_workout(workout), indent=2)
