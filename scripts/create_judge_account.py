"""Create or rotate the demonstration accounts, and keep the password out of the repo.

The judge signs in with the account whose credentials are transmitted in the
Devpost form — never in this repository (the rule of the project: no test
password in the code, the documentation or the history).

What the script does:

1. finds the Cognito user pool of the portal (``marge-dev-portal``);
2. generates a strong password for each demonstration account — the five
   roles of the specification and the judge account;
3. creates or updates the users and puts them in their role group;
4. stores the credentials in **AWS Secrets Manager** (one secret, JSON), so
   the password is never written in a file, a log or a commit;
5. prints the ARN of the secret and the command to read it — never the
   password itself.

Usage::

    python3 scripts/create_judge_account.py --region eu-west-1
    python3 scripts/create_judge_account.py --region eu-west-1 --rotate-demo-users
    aws secretsmanager get-secret-value --secret-id marge/demo/credentials --region eu-west-1
"""

from __future__ import annotations

import argparse
import contextlib
import json
import secrets
import string
import sys
from typing import Any

DEFAULT_REGION = "eu-west-1"
DEFAULT_POOL_NAME = "marge-dev-portal"
DEFAULT_SECRET_ID = "marge/demo/credentials"
JUDGE_LOGIN = "judge@marge.demo"
JUDGE_GROUP = "CONTROLLER"

DEMO_USERS = {
    "director-01@marge.demo": "EXECUTIVE",
    "ops-01@marge.demo": "OPERATIONS_DIRECTOR",
    "am-01@marge.demo": "ACCOUNT_MANAGER",
    "controller-01@marge.demo": "CONTROLLER",
    "admin-01@marge.demo": "ADMINISTRATOR",
}
"""The five roles of the specification (spec 6) — one account each."""


def strong_password(length: int = 20) -> str:
    """A password that satisfies the Cognito policy of the user pool.

    Twelve characters minimum, one upper case, one lower case, one digit and
    one symbol — the policy of ``infra/cdk/portal.py``.
    """
    symbols = "!@#$%^&*-_=+"
    alphabet = string.ascii_letters + string.digits + symbols
    while True:
        candidate = "".join(secrets.choice(alphabet) for _ in range(length))
        if (
            any(c.isupper() for c in candidate)
            and any(c.islower() for c in candidate)
            and any(c.isdigit() for c in candidate)
            and any(c in symbols for c in candidate)
        ):
            return candidate


def find_pool(identity: Any, pool_name: str) -> str:
    """The id of the user pool of the portal."""
    paginator = identity.get_paginator("list_user_pools")
    for page in paginator.paginate(MaxResults=60):
        for pool in page.get("UserPools", []):
            if pool.get("Name") == pool_name:
                return pool["Id"]
    raise SystemExit(f"user pool not found: {pool_name} (deploy the portal stack first)")


def upsert_user(identity: Any, pool_id: str, login: str, password: str) -> None:
    """Create the user if needed, set its password, confirm it."""
    with contextlib.suppress(identity.exceptions.UsernameExistsException):
        identity.create_user(UserPoolId=pool_id, Username=login, MessageAction="SUPPRESS")
    identity.admin_set_user_password(
        UserPoolId=pool_id,
        Username=login,
        Password=password,
        Permanent=True,
    )
    identity.admin_update_user_attributes(
        UserPoolId=pool_id,
        Username=login,
        UserAttributes=[{"Name": "email", "Value": login}],
    )


def add_to_group(identity: Any, pool_id: str, login: str, group: str) -> None:
    """Put the user in its role group — that is what the API reads."""
    identity.admin_add_user_to_group(UserPoolId=pool_id, Username=login, GroupName=group)


def store_secret(secrets_client: Any, secret_id: str, payload: dict[str, str]) -> str:
    """Keep the credentials in Secrets Manager, never in a file."""
    body = json.dumps(payload, indent=2, sort_keys=True)
    try:
        response = secrets_client.create_secret(Name=secret_id, SecretString=body)
    except secrets_client.exceptions.ResourceExistsException:
        response = secrets_client.update_secret(SecretId=secret_id, SecretString=body)
    return response["ARN"]


def main(argv: list[str] | None = None) -> int:
    """Rotate the demonstration passwords and publish the judge account."""
    import boto3

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--region", default=DEFAULT_REGION)
    parser.add_argument("--pool-id", default="", help="default: the pool named marge-dev-portal")
    parser.add_argument("--pool-name", default=DEFAULT_POOL_NAME)
    parser.add_argument("--secret-id", default=DEFAULT_SECRET_ID)
    parser.add_argument("--judge-login", default=JUDGE_LOGIN)
    parser.add_argument("--judge-group", default=JUDGE_GROUP)
    parser.add_argument(
        "--rotate-demo-users",
        action="store_true",
        help="also rotate the password of the five role accounts",
    )
    args = parser.parse_args(argv)

    identity = boto3.client("cognito-idp", region_name=args.region)
    secrets_client = boto3.client("secrets-manager", region_name=args.region)
    pool_id = args.pool_id or find_pool(identity, args.pool_name)

    credentials: dict[str, str] = {}
    judge_password = strong_password()
    upsert_user(identity, pool_id, args.judge_login, judge_password)
    add_to_group(identity, pool_id, args.judge_login, args.judge_group)
    credentials[args.judge_login] = judge_password
    print(f"judge account ready: {args.judge_login} (group {args.judge_group})")

    if args.rotate_demo_users:
        for login, group in DEMO_USERS.items():
            password = strong_password()
            upsert_user(identity, pool_id, login, password)
            add_to_group(identity, pool_id, login, group)
            credentials[login] = password
        print(f"rotated {len(DEMO_USERS)} demonstration accounts")

    arn = store_secret(secrets_client, args.secret_id, credentials)
    print(f"secret: {arn}")
    print(
        f"read it with: aws secretsmanager get-secret-value --secret-id {args.secret_id} "
        f"--region {args.region} --query SecretString --output text"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
