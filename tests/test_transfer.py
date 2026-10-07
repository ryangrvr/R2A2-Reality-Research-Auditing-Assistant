"""Transfer machinery tests: the signature feature."""
import pytest

from r2a2.transfer import FrozenParameter, SectorDemand, audit_transfer


def _frozen():
    return {
        "theta_1": FrozenParameter("theta_1", "A", 1.0),
        "theta_2": FrozenParameter("theta_2", "A", 2.0),
    }


def test_clean_transfer_passes():
    v = audit_transfer(_frozen(), SectorDemand("B", required=["theta_1", "theta_2"]))
    assert v.outcome == "PASS"
    out = v.render("A", "B")
    assert "No transferred parameter was refit" in out
    assert all(l["status"] == "FROZEN" for l in v.lines)


def test_new_parameter_fails():
    v = audit_transfer(_frozen(),
                       SectorDemand("B", required=["theta_1", "phi_1"],
                                    introduced=["phi_1"]))
    assert v.outcome == "FAIL"
    assert any(l["status"] == "NEW INPUT" for l in v.lines)
    assert "unpriced sector-specific parameter" in " ".join(v.reasons)


def test_unresolved_parameter_fails():
    v = audit_transfer(_frozen(), SectorDemand("B", required=["theta_1", "phi_1"]))
    assert v.outcome == "FAIL"
    assert any(l["status"] == "UNRESOLVED" for l in v.lines)


def test_silent_refit_fails():
    v = audit_transfer(_frozen(), SectorDemand("B", required=["theta_1"]),
                       refit={"theta_1": "B"})
    assert v.outcome == "FAIL"
    assert any(l["status"] == "SILENT REFIT" for l in v.lines)


def test_declared_refit_is_legal():
    """A refit is a legal *declared* stance: the claim stops being a pure
    transfer, but it is not a violation."""
    v = audit_transfer(_frozen(),
                       SectorDemand("B", required=["theta_1"], introduced=["theta_1"]),
                       refit={"theta_1": "B"})
    assert v.outcome == "PASS"
    assert any("declared" in l["status"] for l in v.lines)


def test_data_overlap_fails():
    v = audit_transfer(_frozen(),
                       SectorDemand("B", required=["theta_1", "theta_2"],
                                    calibration_data_overlap=["D1"]))
    assert v.outcome == "FAIL"
    assert "not out-of-sample" in " ".join(v.reasons)
