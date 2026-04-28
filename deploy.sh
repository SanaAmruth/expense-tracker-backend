#!/bin/bash
# AWS Lambda Deployment Script for Expense Tracker Backend

set -e  # Exit on error

echo "🚀 Starting AWS Lambda Deployment..."

# Configuration
FUNCTION_NAME="expense-tracker-backend"
RUNTIME="python3.11"
HANDLER="lambda_handler.handler"
TIMEOUT="180"
MEMORY="512"
REGION="us-east-1"

# Step 1: Create deployment package
echo "📦 Creating deployment package..."
rm -rf lambda_package
mkdir lambda_package
cd lambda_package

# Install dependencies
python -m pip install --upgrade pip
python -m pip install -r ../requirements-lambda.txt -t .

# Copy application code
cp ../main.py .
cp ../lambda_handler.py .

# Create deployment zip
zip -r ../lambda_deployment.zip . > /dev/null
cd ..

echo "✅ Deployment package created (lambda_deployment.zip)"

# Step 2: Create or update Lambda function
echo "🔧 Creating/updating Lambda function..."

if aws lambda get-function --function-name "$FUNCTION_NAME" --region "$REGION" 2>/dev/null; then
    echo "Function exists. Updating..."
    aws lambda update-function-code \
        --function-name "$FUNCTION_NAME" \
        --zip-file fileb://lambda_deployment.zip \
        --region "$REGION"
    
    # Wait for update to complete
    aws lambda wait function-updated --function-name "$FUNCTION_NAME" --region "$REGION"
    echo "✅ Lambda function updated"
else
    echo "Function doesn't exist. Creating..."
    aws lambda create-function \
        --function-name "$FUNCTION_NAME" \
        --runtime "$RUNTIME" \
        --role "arn:aws:iam::$(aws sts get-caller-identity --query Account --output text):role/lambda-execution-role" \
        --handler "$HANDLER" \
        --timeout "$TIMEOUT" \
        --memory-size "$MEMORY" \
        --zip-file fileb://lambda_deployment.zip \
        --region "$REGION"
    echo "✅ Lambda function created"
fi

# Step 3: Add environment variables
echo "🔐 Setting environment variables..."
ALLOWED_ORIGINS_VALUE="${ALLOWED_ORIGINS:-https://expense-tracker-frontend-a.netlify.app}"

if [ -z "${OPENAI_API_KEY:-}" ]; then
    echo "❌ OPENAI_API_KEY is not set. Add it as a GitHub Actions secret and pass it to the workflow." >&2
    exit 1
fi

aws lambda update-function-configuration \
    --function-name "$FUNCTION_NAME" \
    --environment "Variables={ALLOWED_ORIGINS=$ALLOWED_ORIGINS_VALUE,OPENAI_API_KEY=$OPENAI_API_KEY}" \
    --region "$REGION" > /dev/null

echo "✅ Environment variables set"

# Step 4: Create or check API Gateway
echo "🌐 Checking API Gateway..."

API_ID=$(aws apigateway get-rest-apis --region "$REGION" --query "items[?name=='$FUNCTION_NAME'].id" --output text 2>/dev/null || echo "")

if [ -z "$API_ID" ]; then
    echo "Creating API Gateway..."
    API_ID=$(aws apigateway create-rest-api \
        --name "$FUNCTION_NAME" \
        --description "API Gateway for Expense Tracker Backend" \
        --region "$REGION" \
        --query 'id' \
        --output text)
fi

echo "✅ Using API Gateway: $API_ID"

ROOT_ID=$(aws apigateway get-resources \
    --rest-api-id "$API_ID" \
    --region "$REGION" \
    --query 'items[?path==`/`].id | [0]' \
    --output text)

# Ensure proxy resource exists (catches /anything)
PROXY_RESOURCE=$(aws apigateway get-resources \
    --rest-api-id "$API_ID" \
    --region "$REGION" \
    --query 'items[?pathPart==`{proxy+}`].id | [0]' \
    --output text)

if [ -z "$PROXY_RESOURCE" ] || [ "$PROXY_RESOURCE" = "None" ]; then
    PROXY_RESOURCE=$(aws apigateway create-resource \
        --rest-api-id "$API_ID" \
        --parent-id "$ROOT_ID" \
        --path-part "{proxy+}" \
        --region "$REGION" \
        --query 'id' \
        --output text)
fi

LAMBDA_URI="arn:aws:apigateway:$REGION:lambda:path/2015-03-31/functions/arn:aws:lambda:$REGION:$(aws sts get-caller-identity --query Account --output text):function:$FUNCTION_NAME/invocations"

# Important: configure BOTH "/" and "/{proxy+}".
# If "/" isn't configured, hitting the base URL often returns:
# {"message":"Missing Authentication Token"}
for RESOURCE_ID in "$ROOT_ID" "$PROXY_RESOURCE"; do
    aws apigateway put-method \
        --rest-api-id "$API_ID" \
        --resource-id "$RESOURCE_ID" \
        --http-method ANY \
        --authorization-type NONE \
        --region "$REGION" > /dev/null 2>&1 || true

    aws apigateway put-integration \
        --rest-api-id "$API_ID" \
        --resource-id "$RESOURCE_ID" \
        --http-method ANY \
        --type AWS_PROXY \
        --integration-http-method POST \
        --uri "$LAMBDA_URI" \
        --region "$REGION" > /dev/null
done

# Add/ensure Lambda permission (idempotent)
aws lambda add-permission \
    --function-name "$FUNCTION_NAME" \
    --statement-id apigateway-access \
    --action lambda:InvokeFunction \
    --principal apigateway.amazonaws.com \
    --source-arn "arn:aws:execute-api:$REGION:$(aws sts get-caller-identity --query Account --output text):$API_ID/*/*" \
    --region "$REGION" 2>/dev/null || true

# Always (re)deploy API so changes take effect
aws apigateway create-deployment \
    --rest-api-id "$API_ID" \
    --stage-name "prod" \
    --region "$REGION" > /dev/null

API_ENDPOINT="https://$API_ID.execute-api.$REGION.amazonaws.com/prod"

# Step 5: Display results
echo ""
echo "================================"
echo "✅ DEPLOYMENT SUCCESSFUL!"
echo "================================"
echo "Your API endpoint is:"
echo "🌐 $API_ENDPOINT"
echo ""
echo "Update your frontend with:"
echo "EXPO_PUBLIC_VOICE_API_URL=$API_ENDPOINT/voice-expense"
echo "================================"

# Cleanup
rm -rf lambda_package lambda_deployment.zip

echo "🎉 Done!"
