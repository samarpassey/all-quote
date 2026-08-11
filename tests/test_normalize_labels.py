"""Completeness guards for the label-mapping data tables: these must fail
loudly if the dimension enum or the intake schema drifts out from under
them, per the approved plan for Task 8.
"""

from allquote.intake import OPTIONAL_AB_BENEFITS
from allquote.normalize_basis import _ENDORSEMENT_KEY_BY_DIMENSION
from allquote.normalize_labels import AB_OPT_KEY_MAP, BASIS_DEFAULTS
from allquote.schemas import REQUESTABLE_DIMENSIONS, CoverageDimension


def test_ab_opt_key_map_covers_exactly_the_13_intake_short_keys():
    assert set(AB_OPT_KEY_MAP) == set(OPTIONAL_AB_BENEFITS)
    assert len(AB_OPT_KEY_MAP) == 13


def test_basis_defaults_covers_exactly_the_dimensions_coverage_benchmark_lacks():
    directly_covered = (
        {CoverageDimension.THIRD_PARTY_LIABILITY, CoverageDimension.DCPD, CoverageDimension.OWN_DAMAGE_COLLISION, CoverageDimension.OWN_DAMAGE_COMPREHENSIVE}
        | set(_ENDORSEMENT_KEY_BY_DIMENSION)
        | set(AB_OPT_KEY_MAP.values())
    )
    expected_defaults = REQUESTABLE_DIMENSIONS - directly_covered
    assert set(BASIS_DEFAULTS) == expected_defaults
    assert set(BASIS_DEFAULTS) == {
        CoverageDimension.ACCIDENT_BENEFITS_MANDATORY,
        CoverageDimension.UNINSURED_AUTOMOBILE,
        CoverageDimension.OWN_DAMAGE_SPECIFIED_PERILS,
        CoverageDimension.OWN_DAMAGE_ALL_PERILS,
        CoverageDimension.OPCF_49_DCPD_OPT_OUT,
    }
