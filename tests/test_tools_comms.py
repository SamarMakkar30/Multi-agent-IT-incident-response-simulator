"""Unit tests for Comms Agent domain tools."""

from war_room.tools.comms_tools import (
    check_comms_policy,
    get_status_template,
    render_status_update,
)


def test_status_template_and_rendering():
    tmpl = get_status_template(severity="SEV1")
    assert "{service}" in tmpl
    assert "{user_impact}" in tmpl

    rendered = render_status_update(
        template=tmpl,
        service="checkout-service",
        status="Mitigating with rollback",
        user_impact="Customers experiencing payment errors at checkout",
    )
    assert "checkout-service" in rendered
    assert "payment errors at checkout" in rendered


def test_check_comms_policy_clean():
    clean_text = "We have rolled back the release and service latency has restored."
    check = check_comms_policy(clean_text)
    assert check.compliant is True
    assert len(check.violations) == 0


def test_check_comms_policy_violations():
    violating = (
        "Server 10.0.4.12 crashed with at com.company.checkout.CheckoutController.java:84. "
        "Contact dev-alice@company.internal"
    )
    check = check_comms_policy(violating)
    assert check.compliant is False
    assert len(check.violations) == 3
    assert any("IP" in v for v in check.violations)
    assert any("email" in v for v in check.violations)
    assert any("stack trace" in v for v in check.violations)
