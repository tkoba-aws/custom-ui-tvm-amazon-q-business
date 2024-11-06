# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import os
import json
import boto3
import base64
import logging

log_level = os.environ.get('LOG_LEVEL', 'DEBUG')
logger = logging.getLogger(__name__)
logger.setLevel(log_level)

ssm_client = boto3.client('ssm')

# SSM Parameter Name
ALLOW_LIST_PARAM = os.getenv('OIDC_ALLOW_LIST')
CLIENT_ID_PARAM = os.getenv("CLIENT_ID_PARAM")
CLIENT_SECRET_PARAM = os.getenv("CLIENT_SECRET_PARAM")

def get_client_credentials():
    client_id = ssm_client.get_parameter(Name=CLIENT_ID_PARAM)['Parameter']['Value']
    client_secret = ssm_client.get_parameter(Name=CLIENT_SECRET_PARAM, WithDecryption=True)['Parameter']['Value']
    return client_id, client_secret

# Fetch the allow-listed domains from SSM
def get_allow_list():
    try:
        response = ssm_client.get_parameter(Name=ALLOW_LIST_PARAM)
        allow_list = response['Parameter']['Value'].split(',')
        return [domain.strip() for domain in allow_list]
    except Exception as e:
        logger.error(f"Error fetching allow-list: {str(e)}")
        return []

def lambda_handler(event, context):
    logger.debug(json.dumps(event))
    method_arn = event['methodArn']
    # path = event['requestContext']['resourcePath']
    headers = event.get('headers', {})
    origin = headers.get('origin')  # Get the Origin header
    auth_header = headers.get('Authorization')  # Get the Authorization header
    
    logger.info(f"Request origin: {origin}")

    if event['httpMethod'] == 'OPTIONS':
        return generate_policy("Allow", method_arn)

    allow_list = get_allow_list()
    stored_client_id, stored_client_secret = get_client_credentials()

    if origin in allow_list:
        # Scenario 1: Allow-listed origin, allow the request without checking credentials
        logger.info("Request from authorized domain...")
        return generate_policy("Allow", method_arn)

    elif auth_header and auth_header.startswith("Basic "):
        # Scenario 2: Backend caller with client ID and secret in the header
        logger.info("Request from unauthorized domain...checking client ID and secret")
        encoded_credentials = auth_header.split(' ')[1]
        decoded_credentials = base64.b64decode(encoded_credentials).decode('utf-8')
        client_id, client_secret = decoded_credentials.split(':')

        if client_id == stored_client_id and client_secret == stored_client_secret:
            return generate_policy("Allow", method_arn)
        else:
            return generate_policy("Deny", method_arn)

    # Deny the request if neither allow-listed origin nor valid credentials are provided
    return generate_policy("Deny", method_arn)

def generate_policy(effect, resource):
    """Generate an IAM policy."""
    policy = {
        "principalId": "user",
        "policyDocument": {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Action": "execute-api:Invoke",
                    "Effect": effect,
                    "Resource": resource
                }
            ]
        }
    }
    return policy