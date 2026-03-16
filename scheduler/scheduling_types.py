from __future__ import annotations
from enum import Enum
from functools import total_ordering
from typing import (
    Annotated,
    Generic,
    List,
    Literal,
    Optional,
    TypeVar,
    Union,
)
from pydantic import BaseModel, Field

BrickType = Literal[
    "FWS",
    "FAW",
    "FQR",
    "FIE",
    "PHTC",
    "PHA",
    "PNS",
    "PSBS",
    "ACSW",
    "ANW",
    "ACNW",
    "BSL",
    "BER",
    "BDP",
    "BLD",
    "CAP",
]


class OfferingPattern(str, Enum):
    SUMMER = "summer"
    FALL_AND_SPRING = "fall_and_spring"
    FALL = "fall"
    SPRING = "spring"
    FALL_EVEN = "fall_even"
    FALL_ODD = "fall_odd"
    SPRING_EVEN = "spring_even"
    SPRING_ODD = "spring_odd"
    SUMMER_EVEN = "summer_even"
    SUMMER_ODD = "summer_odd"
    IRREGULAR = "irregular"
    ARRANGED = "arranged"
    DEACTIVATED = "deactivated"
    UNKNOWN = "unknown"  # default for missing/invalid patterns


class RequirementType(str, Enum):
    NONE = "NONE"
    PERMISSION = "PERMISSION"
    LEVEL = "LEVEL"
    PLACEMENT = "PLACEMENT"
    GPA = "GPA"
    COURSE = "COURSE"
    OR = "OR"
    AND = "AND"
    CREDITS_FROM = "CREDITS_FROM"
    CHOOSE_N = "CHOOSE_N"
    OTHER = "OTHER"


T = TypeVar("T", bound=RequirementType)


# Base requirement types
class BaseRequirement(BaseModel, Generic[T]):
    type: T


class Course(BaseRequirement):
    type: Literal[RequirementType.COURSE] = RequirementType.COURSE
    course: str
    timing: Literal["COMPLETED", "CONCURRENT", "CONCURRENT_OR_COMPLETED"]


class GPA(BaseRequirement):
    type: Literal[RequirementType.GPA] = RequirementType.GPA
    gpa: float


@total_ordering
class Placement(BaseRequirement):
    type: Literal[RequirementType.PLACEMENT] = RequirementType.PLACEMENT
    subject: str
    level: str

    def _rank(self) -> int:
        if self.level.isdigit():
            return int(self.level)
        return 0  # DV / unknown

    def __lt__(self, other: "Placement") -> bool:
        if not isinstance(other, Placement):
            return NotImplemented
        return self._rank() < other._rank()

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Placement):
            return False
        return self._rank() == other._rank()


class Permission(BaseRequirement):
    type: Literal[RequirementType.PERMISSION] = RequirementType.PERMISSION
    authority: str


@total_ordering
class Level(BaseRequirement):
    type: Literal[RequirementType.LEVEL] = RequirementType.LEVEL
    level: Literal["freshman", "sophomore", "junior", "senior"]

    _level_order = {"freshman": 0, "sophomore": 1, "junior": 2, "senior": 3}

    def __eq__(self, other):
        if not isinstance(other, Level):
            return NotImplemented
        return self.level == other.level

    def __lt__(self, other):
        if not isinstance(other, Level):
            return NotImplemented
        return self._level_order[self.level] < self._level_order[other.level]


class Other(BaseRequirement):
    type: Literal[RequirementType.OTHER] = RequirementType.OTHER
    other: str


class Empty(BaseRequirement):
    type: Literal[RequirementType.NONE] = RequirementType.NONE


# Recursive requirement types
class Or(BaseRequirement):
    type: Literal[RequirementType.OR] = RequirementType.OR
    requirements: list[Requirement]


class And(BaseRequirement):
    type: Literal[RequirementType.AND] = RequirementType.AND
    requirements: list[Requirement]


class CreditsFrom(BaseRequirement):
    type: Literal[RequirementType.CREDITS_FROM] = RequirementType.CREDITS_FROM
    credits_required: float
    requirements: List[Requirement]


class ChooseN(BaseRequirement):
    type: Literal[RequirementType.CHOOSE_N] = RequirementType.CHOOSE_N
    choose: int
    requirements: List[Requirement]


Requirement = Annotated[
    Union[
        Or,
        And,
        Course,
        GPA,
        Placement,
        Permission,
        Level,
        Other,
        Empty,
        CreditsFrom,
        ChooseN,
    ],
    Field(discriminator="type"),
]


class Program(BaseModel):
    catalog_name: str
    catalog_year: int
    catalog_archived: bool
    program_type: str
    program_name: str
    program_link: str
    credits: int
    code: str
    requisite: List[Requirement]


class Config(BaseModel):
    program: Program
    completed_course_work: List[str]
    placements: List[Placement]
    gpa: float
    level: Level
    credits_per_semester: int
    start_year: int
    start_term: Literal["fall", "spring"]


class ParsedCourse(BaseModel):
    name: str
    code: str
    requisite_string: Optional[str]
    requisite: List[Requirement]
    component: str
    bricks: List[str]
    min_credits: float
    max_credits: float
    pattern: OfferingPattern
