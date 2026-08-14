#!/bin/bash

DLQ_URL=$(awslocal sqs create-queue --queue-name skryzhal-render-dlq --query 'QueueUrl' --output text)
DLQ_ARN=$(awslocal sqs get-queue-attributes --queue-url "$DLQ_URL" --attribute-names QueueArn --query 'Attributes.QueueArn' --output text)

awslocal sqs create-queue --queue-name skryzhal-render-queue --attributes "{\"VisibilityTimeout\":\"30\",\"RedrivePolicy\":\"{\\\"deadLetterTargetArn\\\":\\\"$DLQ_ARN\\\",\\\"maxReceiveCount\\\":\\\"3\\\"}\"}"

echo "SQS queues created: skryzhal-render-queue (VisibilityTimeout=30s) + DLQ skryzhal-render-dlq (maxReceiveCount=3)"
