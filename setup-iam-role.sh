#!/bin/bash
# Setup IAM role for Lambda execution

echo "Setting up IAM role for Lambda..."

ROLE_NAME="lambda-execution-role"
REGION="us-east-1"

# Create role
aws iam create-role \
    --role-name "$ROLE_NAME" \
    --assume-role-policy-document '{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "lambda.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}' 2>/dev/null || echo "Role already exists"

# Attach basic execution policy
aws iam attach-role-policy \
    --role-name "$ROLE_NAME" \
    --policy-arn "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole" \
    2>/dev/null || true

echo "✅ IAM role ready!"
