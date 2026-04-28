"""
AWS Lambda handler for FastAPI application.
This file bridges between AWS Lambda and your FastAPI app.
"""
from mangum import Mangum
from main import app

# Create the Lambda handler
handler = Mangum(app, lifespan="off")
