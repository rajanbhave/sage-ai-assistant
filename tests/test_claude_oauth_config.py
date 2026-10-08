import pytest

from scripts.configure_claude_oauth import OAUTH_FIELDS, oauth_parameters


def test_oauth_update_preserves_client_settings_and_existing_callbacks():
    client = {"UserPoolId": "pool", "ClientId": "client", "ExplicitAuthFlows": ["ALLOW_USER_SRP_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"], "AccessTokenValidity": 60, "TokenValidityUnits": {"AccessToken": "minutes"}, "ReadAttributes": ["custom:tenant_assignment"], "WriteAttributes": [], "EnableTokenRevocation": True, "CallbackURLs": ["https://app.example/callback"]}
    updated = oauth_parameters(client)
    assert {k: v for k, v in updated.items() if k not in OAUTH_FIELDS} == {k: v for k, v in client.items() if k not in OAUTH_FIELDS}
    assert "https://app.example/callback" in updated["CallbackURLs"]
    assert client["CallbackURLs"] == ["https://app.example/callback"]
    assert updated["AllowedOAuthFlows"] == ["code"]
    with pytest.raises(ValueError, match="public client"):
        oauth_parameters({**client, "ClientSecret": "synthetic-test-value"})
    with pytest.raises(ValueError, match="M2M"):
        oauth_parameters({**client, "AllowedOAuthFlows": ["client_credentials"]})
