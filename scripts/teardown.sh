#!/usr/bin/env bash
# Delete the whole Marge demonstration environment.
#
# The stacks keep the buckets and the validation table (RemovalPolicy.RETAIN):
# the demonstration data must survive an accidental deploy. This script is the
# opposite — it empties what CloudFormation keeps, then destroys everything.
#
#   bash scripts/teardown.sh            # the stacks and the retained resources
#   bash scripts/teardown.sh --data     # the demonstration data only
#
# Cost: nothing is billed, everything is destroyed.
set -euo pipefail
export LC_ALL=C

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

export AWS_REGION="${AWS_REGION:-eu-west-1}"
export AWS_DEFAULT_REGION="$AWS_REGION"
CDK_APP="${CDK_APP:-cdk}"
DATA_ONLY=0
[ "${1:-}" = "--data" ] && DATA_ONLY=1

stack_output() { # $1 = stack, $2 = output key
  aws cloudformation describe-stacks --stack-name "$1" --region "$AWS_REGION" \
    --query "Stacks[0].Outputs[?OutputKey=='$2'].OutputValue" --output text 2>/dev/null || echo ""
}

empty_bucket() { # $1 = bucket name
  [ -z "$1" ] && return 0
  echo "  emptying s3://$1"
  python3 scripts/empty_bucket.py "$1"
}

delete_table() { # $1 = table name
  [ -z "$1" ] && return 0
  echo "  deleting table $1"
  aws dynamodb delete-table --region "$AWS_REGION" --table-name "$1" >/dev/null 2>&1 || true
}

echo "== Ressources conservées (RETAIN) =="
for bucket in \
  "$(stack_output MargeDataLake RawBucketName)" \
  "$(stack_output MargeDataLake CuratedBucketName)" \
  "$(stack_output MargePortal PortalSiteBucket)" \
  "$(stack_output MargeQuickSight AssetBucketName)"; do
  empty_bucket "$bucket"
done
delete_table "$(stack_output MargePortal ValidationTableName)"

if [ "$DATA_ONLY" = "1" ]; then
  echo "== Données de démonstration supprimées =="
  exit 0
fi

echo "== Destruction des stacks =="
cd "$ROOT/infra/cdk"
$CDK_APP destroy --all --require-approval never
echo "== Environnement supprimé =="
