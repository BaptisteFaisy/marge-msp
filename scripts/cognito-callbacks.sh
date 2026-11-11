#!/usr/bin/env bash
# Point the Cognito Hosted UI at the deployed portal.
#
# The callback URLs depend on the CloudFront name, which depends on the API,
# which depends on the Lambda, which needs the client id: setting them inside
# the stack would be a CloudFormation cycle. They are therefore set here, once,
# after the deployment. The command is idempotent.
#
# Usage : scripts/cognito-callbacks.sh [region] [stack] [profile]
set -euo pipefail
export LC_ALL=C

REGION="${1:-${AWS_REGION:-eu-west-1}}"
STACK="${2:-MargePortal}"
PROFILE="${3:-}"

aws_args=(--region "$REGION")
[ -n "$PROFILE" ] && aws_args+=(--profile "$PROFILE")

url() { aws "${aws_args[@]}" cloudformation describe-stacks --stack-name "$STACK" \
  --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" --output text; }

POOL="$(url UserPoolId)"
CLIENT="$(url UserPoolClientId)"
DOMAIN="$(url HostedUiUrl)"; DOMAIN="${DOMAIN%%/login*}"
PORTAL="$(url PortalUrl)"
[ -n "$POOL" ] && [ -n "$CLIENT" ] || { echo "stack $STACK has no Cognito outputs"; exit 1; }

CALLBACK="${PORTAL%/}/"
CALLBACK_ALT="${PORTAL%/}/index.html"
LOGOUT="${PORTAL%/}/"

echo "pool=$POOL client=$CLIENT"
echo "callback=$CALLBACK"
aws "${aws_args[@]}" cognito-idp update-user-pool-client \
  --user-pool-id "$POOL" --client-id "$CLIENT" \
  --allowed-o-auth-flows implicit \
  --allowed-o-auth-scopes openid email profile \
  --callback-urls "$CALLBACK" "$CALLBACK_ALT" \
  --logout-urls "$LOGOUT" "$CALLBACK_ALT" \
  --supported-identity-providers COGNITO \
  --allowed-o-auth-flows-user-pool-client \
  --explicit-auth-flows ALLOW_USER_PASSWORD_AUTH ALLOW_REFRESH_TOKEN_AUTH \
  >/dev/null

echo "Hosted UI : https://${DOMAIN}/login?client_id=${CLIENT}&response_type=token&scope=openid+email+profile&redirect_uri=${CALLBACK}"
echo "OK"
