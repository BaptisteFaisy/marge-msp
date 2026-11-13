#!/usr/bin/env bash
# Deploy the Marge demonstration environment, end to end.
#
# One command, idempotent: build the Lambda packages, deploy the stacks,
# load the demonstration dataset and publish the analytical tables.
#
#   bash scripts/deploy.sh
#
# Environment (all optional, the defaults are the reference deployment):
#   AWS_REGION          eu-west-1    the region of the deployment
#   MARGE_AUTH_MODE     cognito       the portal refuses to trust headers
#   MARGE_BUDGET_EMAIL  (empty)      the mailbox that receives the alerts
#   CDK_APP             cdk           the command that synthesises the stacks
set -euo pipefail
export LC_ALL=C

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

export AWS_REGION="${AWS_REGION:-eu-west-1}"
export AWS_DEFAULT_REGION="$AWS_REGION"
export MARGE_AUTH_MODE="${MARGE_AUTH_MODE:-cognito}"
CDK_APP="${CDK_APP:-cdk}"

stack_output() { # $1 = stack, $2 = output key
  aws cloudformation describe-stacks --stack-name "$1" --region "$AWS_REGION" \
    --query "Stacks[0].Outputs[?OutputKey=='$2'].OutputValue" --output text
}

echo "== 1/4 Paquets Lambda =="
bash scripts/build-lambda-package.sh

echo "== 2/4 Synthèse =="
cd "$ROOT/infra/cdk"
$CDK_APP synth --quiet

echo "== 3/4 Déploiement =="
$CDK_APP deploy --all --require-approval never
cd "$ROOT"

CURATED="${MARGE_CURATED_BUCKET:-$(stack_output MargeDataLake CuratedBucketName)}"
TABLE="${MARGE_TABLE:-$(stack_output MargePortal ValidationTableName)}"

echo "== 4/4 Jeu de démonstration =="
python3 -m marge.cli load-demo \
  --backend dynamo \
  --table "$TABLE" \
  --region "$AWS_REGION" \
  --publish-s3 "$CURATED"

echo "== Terminé =="
echo "portail : $(stack_output MargePortal PortalUrl)"
