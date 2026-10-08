"""Render or apply OAuth settings while preserving an existing public client."""

import argparse
import json
from pathlib import Path

import boto3

CALLBACK = "https://claude.ai/api/mcp/auth_callback"
SCOPES = {"openid", "sage-agent/invoke", "sage-gateway/invoke", "sage-mcp/invoke", "sage-api/read"}
OAUTH_FIELDS = {"CallbackURLs", "AllowedOAuthFlows", "AllowedOAuthScopes", "AllowedOAuthFlowsUserPoolClient", "SupportedIdentityProviders"}


def oauth_parameters(client):
    if client.get("ClientSecret"):
        raise ValueError("Reuse requires a public client without a secret")
    if "client_credentials" in client.get("AllowedOAuthFlows", []):
        raise ValueError("Cannot add code flow to an M2M client")
    result = {k: v for k, v in client.items() if k not in {"CreationDate", "LastModifiedDate", "ClientSecret"}}
    for key, values in (
        ("CallbackURLs", {CALLBACK}),
        ("AllowedOAuthFlows", {"code"}),
        ("AllowedOAuthScopes", SCOPES),
        ("SupportedIdentityProviders", {"COGNITO"}),
    ):
        result[key] = sorted(set(client.get(key, [])) | values)
    result["AllowedOAuthFlowsUserPoolClient"] = True
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm", action="store_true")
    args = parser.parse_args()
    manifest = json.loads((Path(__file__).parent / "identity_deployment.json").read_text())
    lane = next(lane for lane in manifest["lanes"] if lane["laneId"] == "Tenant_A")
    idp = boto3.client("cognito-idp", region_name=manifest["region"])
    original = idp.describe_user_pool_client(UserPoolId=lane["userPoolId"], ClientId=lane["frontendClientIds"][0])["UserPoolClient"]
    parameters = oauth_parameters(original)
    allowed = idp.meta.service_model.operation_model("UpdateUserPoolClient").input_shape.members
    if parameters.keys() - allowed.keys():
        raise ValueError("SDK cannot preserve all existing client fields")
    print(json.dumps({key: parameters[key] for key in sorted(OAUTH_FIELDS)}, indent=2))
    if args.confirm:
        idp.update_user_pool_client(**parameters)
        actual = idp.describe_user_pool_client(UserPoolId=lane["userPoolId"], ClientId=lane["frontendClientIds"][0])["UserPoolClient"]
        for key, value in parameters.items():
            observed = actual.get(key)
            if isinstance(value, list):
                value, observed = sorted(value), sorted(observed or [])
            if value != observed:
                raise RuntimeError(f"Client readback differs for {key}")
        print("OAuth enabled; all existing client settings preserved and verified")


if __name__ == "__main__":
    main()
