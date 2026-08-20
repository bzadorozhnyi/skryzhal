#!/bin/bash
set -e

create_bucket() {
  local bucket="$1"

  awslocal s3 mb "s3://$bucket"
  echo "S3 bucket '$bucket' created successfully"

  awslocal s3api put-bucket-cors --bucket "$bucket" --cors-configuration '{
    "CORSRules": [
      {
        "AllowedOrigins": ["*"],
        "AllowedHeaders": ["*"],
        "AllowedMethods": ["GET", "PUT", "POST", "DELETE", "HEAD"],
        "MaxAgeSeconds": 3000
      }
    ]
  }'

  awslocal s3api put-bucket-lifecycle-configuration --bucket "$bucket" --lifecycle-configuration '{
    "Rules": [
      {
        "ID": "expire-staging",
        "Filter": {"Prefix": "staging/"},
        "Status": "Enabled",
        "Expiration": {"Days": 1}
      }
    ]
  }'
  echo "Lifecycle rule 'expire-staging' applied to '$bucket'"
}

create_bucket local-bucket

# Same bucket configuration, dedicated name — so the test suite never
# touches (or races with) the bucket the live api/worker/relay use.
create_bucket test-local-bucket
