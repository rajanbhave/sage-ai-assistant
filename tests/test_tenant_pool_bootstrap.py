"""Guards on the lane pool bootstrap: feature plan and V2_0 trigger attachment."""

from typing import Any

import pytest

from scripts.bootstrap_tenant_pool import (
    ASSIGNMENT_ATTRIBUTE,
    _verify_adopted_pool,
    attach_pre_token_trigger,
)
from tests.env import topology

ALIAS_ARN = topology("SAGE_TEST_TENANT_A_PRE_TOKEN_LAMBDA_ARN")
POOL_ID = topology("SAGE_TEST_TENANT_A_USER_POOL_ID")
POOL_NAME = topology("SAGE_TEST_TENANT_A_POOL_NAME")


class Cognito:
    """In-memory Cognito stub that applies UpdateUserPool to its own state."""

    def __init__(self, pool: dict[str, Any]) -> None:
        self.pool = pool
        self.updates: list[dict[str, Any]] = []

    def describe_user_pool(self, UserPoolId: str):  # noqa: N803 - boto3 casing
        return {"UserPool": dict(self.pool, Id=UserPoolId)}

    def update_user_pool(self, **parameters: Any):
        self.updates.append(parameters)
        self.pool["LambdaConfig"] = parameters["LambdaConfig"]
        return {}


def supported_pool(**overrides: Any) -> dict[str, Any]:
    pool = {
        "Name": POOL_NAME,
        "UserPoolTier": "ESSENTIALS",
        "SchemaAttributes": [
            {"Name": ASSIGNMENT_ATTRIBUTE, "AttributeDataType": "String"}
        ],
        "LambdaConfig": {},
    }
    pool.update(overrides)
    return pool


def test_adopting_a_pool_on_an_unsupported_plan_states_cause_and_fix():
    cognito = Cognito(supported_pool(UserPoolTier="LITE"))

    with pytest.raises(ValueError) as rejected:
        _verify_adopted_pool(cognito, POOL_ID, POOL_NAME)

    message = str(rejected.value)
    assert "cannot deliver V2_0 pre-token events" in message
    assert "only the ID token" in message
    assert "--user-pool-tier ESSENTIALS" in message


def test_attach_writes_v2_config_and_mirrors_the_legacy_field_when_present():
    """The legacy single-version field must not keep pointing somewhere else."""
    cognito = Cognito(
        supported_pool(LambdaConfig={"PreTokenGeneration": ALIAS_ARN.replace(":live", ":stale")})
    )

    attach_pre_token_trigger(cognito, POOL_ID, ALIAS_ARN)

    written = cognito.updates[0]["LambdaConfig"]
    assert written["PreTokenGenerationConfig"] == {
        "LambdaVersion": "V2_0",
        "LambdaArn": ALIAS_ARN,
    }
    assert written["PreTokenGeneration"] == ALIAS_ARN
    # UpdateUserPool resets omitted settings, so the plan must be resent.
    assert cognito.updates[0]["UserPoolTier"] == "ESSENTIALS"


def test_attach_leaves_the_legacy_field_absent_when_the_pool_has_none():
    cognito = Cognito(supported_pool())

    attach_pre_token_trigger(cognito, POOL_ID, ALIAS_ARN)

    assert "PreTokenGeneration" not in cognito.updates[0]["LambdaConfig"]


def test_attach_rejects_a_readback_that_is_not_v2():
    """A silently downgraded trigger would customize only the ID token."""

    class Downgrading(Cognito):
        def update_user_pool(self, **parameters: Any):
            super().update_user_pool(**parameters)
            self.pool["LambdaConfig"] = {
                "PreTokenGenerationConfig": {
                    "LambdaVersion": "V1_0",
                    "LambdaArn": ALIAS_ARN,
                }
            }
            return {}

    with pytest.raises(ValueError, match="readback does not match"):
        attach_pre_token_trigger(Downgrading(supported_pool()), POOL_ID, ALIAS_ARN)


def test_attach_requires_a_qualified_alias_arn():
    cognito = Cognito(supported_pool())

    with pytest.raises(ValueError):
        # An unqualified ARN: the alias or version suffix removed.
        attach_pre_token_trigger(
            cognito, POOL_ID, ALIAS_ARN.rsplit(":", 1)[0]
        )

    assert cognito.updates == []
