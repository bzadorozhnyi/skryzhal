#!/bin/bash

awslocal s3 mb s3://local-bucket

echo "S3 bucket 'local-bucket' created successfully"

awslocal s3api put-bucket-cors --bucket local-bucket --cors-configuration '{
  "CORSRules": [
    {
      "AllowedOrigins": ["*"],
      "AllowedHeaders": ["*"],
      "AllowedMethods": ["GET", "PUT", "POST", "DELETE", "HEAD"],
      "MaxAgeSeconds": 3000
    }
  ]
}'
