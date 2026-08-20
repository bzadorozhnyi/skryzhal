#!/bin/bash
set -e

create_queue_with_dlq() {
  local queue_name="$1"
  local dlq_name="$2"

  local dlq_url dlq_arn
  dlq_url=$(awslocal sqs create-queue --queue-name "$dlq_name" --query 'QueueUrl' --output text)
  dlq_arn=$(awslocal sqs get-queue-attributes --queue-url "$dlq_url" --attribute-names QueueArn --query 'Attributes.QueueArn' --output text)

  awslocal sqs create-queue --queue-name "$queue_name" --attributes "{\"VisibilityTimeout\":\"30\",\"RedrivePolicy\":\"{\\\"deadLetterTargetArn\\\":\\\"$dlq_arn\\\",\\\"maxReceiveCount\\\":\\\"3\\\"}\"}"

  echo "SQS queues created: $queue_name (VisibilityTimeout=30s) + DLQ $dlq_name (maxReceiveCount=3)"
}

create_queue_with_dlq skryzhal-render-queue skryzhal-render-dlq

# Same queue configuration, dedicated names — so the test suite never
# competes with the live api/worker/relay for messages.
create_queue_with_dlq test-skryzhal-render-queue test-skryzhal-render-dlq

# E2E spawns real worker.py/relay.py subprocesses — a dedicated queue pair
# keeps them from racing with the fast in-process test suite above when
# both run at once.
create_queue_with_dlq test-e2e-skryzhal-render-queue test-e2e-skryzhal-render-dlq

# Container restarts replay this script against LocalStack's persisted data
# dir, so any message left behind by a test run that crashed mid-suite would
# otherwise linger and surface as an unexpected redelivery in the next run.
# Only the test queues are purged — the "prod" local ones keep whatever a
# developer has in flight.
for queue_name in test-skryzhal-render-queue test-skryzhal-render-dlq test-e2e-skryzhal-render-queue test-e2e-skryzhal-render-dlq; do
  queue_url=$(awslocal sqs get-queue-url --queue-name "$queue_name" --query 'QueueUrl' --output text)
  awslocal sqs purge-queue --queue-url "$queue_url"
done
echo "Test queues purged"
