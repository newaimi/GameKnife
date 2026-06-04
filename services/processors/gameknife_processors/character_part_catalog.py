from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CharacterPartSpec:
    key: str
    name: str
    prompt: str
    aliases: tuple[str, ...]
    parent_key: str | None
    z_index: int
    pivot: tuple[float, float]
    needs_completion: bool = False


PART_SPECS: dict[str, CharacterPartSpec] = {
    "head": CharacterPartSpec("head", "头部", "head", ("head", "face", "zombie head"), None, 90, (0.5, 0.9)),
    "hair": CharacterPartSpec("hair", "头发", "hair", ("hair", "fur", "mane"), "head", 100, (0.5, 0.75), True),
    "torso": CharacterPartSpec("torso", "躯干", "torso", ("torso", "body", "chest", "jacket", "shirt"), None, 50, (0.5, 0.15)),
    "left_arm": CharacterPartSpec("left_arm", "左臂", "left arm", ("left arm", "left sleeve"), "torso", 42, (0.82, 0.18), True),
    "right_arm": CharacterPartSpec("right_arm", "右臂", "right arm", ("right arm", "right sleeve"), "torso", 58, (0.18, 0.18), True),
    "left_hand": CharacterPartSpec("left_hand", "左手", "left hand", ("left hand", "left claw"), "left_arm", 44, (0.65, 0.18), True),
    "right_hand": CharacterPartSpec("right_hand", "右手", "right hand", ("right hand", "right claw"), "right_arm", 60, (0.35, 0.18), True),
    "left_leg": CharacterPartSpec("left_leg", "左腿", "left leg", ("left leg", "left pants leg"), "torso", 36, (0.55, 0.12), True),
    "right_leg": CharacterPartSpec("right_leg", "右腿", "right leg", ("right leg", "right pants leg"), "torso", 48, (0.45, 0.12), True),
    "left_foot": CharacterPartSpec("left_foot", "左脚", "left foot", ("left foot", "left shoe", "left boot"), "left_leg", 38, (0.5, 0.25)),
    "right_foot": CharacterPartSpec("right_foot", "右脚", "right foot", ("right foot", "right shoe", "right boot"), "right_leg", 50, (0.5, 0.25)),
    "weapon": CharacterPartSpec("weapon", "武器", "weapon", ("weapon", "sword", "gun", "axe", "knife"), None, 110, (0.5, 0.5), True),
    "hat": CharacterPartSpec("hat", "帽子", "hat", ("hat", "helmet", "cap"), "head", 105, (0.5, 0.7), True),
    "tail": CharacterPartSpec("tail", "尾巴", "tail", ("tail",), "torso", 25, (0.2, 0.5), True),
    "wing": CharacterPartSpec("wing", "翅膀", "wing", ("wing", "wings"), "torso", 20, (0.5, 0.5), True),
    "shield": CharacterPartSpec("shield", "盾牌", "shield", ("shield",), None, 108, (0.5, 0.5), True),
    "backpack": CharacterPartSpec("backpack", "背包", "backpack", ("backpack", "bag"), "torso", 18, (0.5, 0.35), True),
}

CORE_PART_KEYS = (
    "head",
    "hair",
    "torso",
    "left_arm",
    "right_arm",
    "left_hand",
    "right_hand",
    "left_leg",
    "right_leg",
    "left_foot",
    "right_foot",
)

OPTIONAL_PART_KEYS = ("weapon", "hat", "tail", "wing", "shield", "backpack")


def normalize_part_key(value: str) -> str | None:
    normalized = value.strip().lower().replace("_", " ").replace("-", " ")
    for key, spec in PART_SPECS.items():
        if normalized == key.replace("_", " ") or normalized == spec.prompt:
            return key
        if normalized in spec.aliases:
            return key
    return None


def part_keys_from_text(text: str) -> list[str]:
    lowered = text.lower()
    keys: list[str] = []
    for key, spec in PART_SPECS.items():
        if key in keys:
            continue
        if spec.prompt in lowered or any(alias in lowered for alias in spec.aliases):
            keys.append(key)
    return keys


def read_part_spec(key: str) -> CharacterPartSpec:
    return PART_SPECS.get(key) or CharacterPartSpec(key, key, key.replace("_", " "), (key.replace("_", " "),), None, 0, (0.5, 0.5), True)
