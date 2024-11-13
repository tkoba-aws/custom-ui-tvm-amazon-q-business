# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import json
import os
import boto3
import datetime
import logging
from authlib.jose import jwt, JsonWebKey

log_level = os.environ.get('LOG_LEVEL', 'DEBUG')
logger = logging.getLogger(__name__)
logger.setLevel(log_level)

# Fetch environment variables
PRIVATE_KEY_PARAM = os.getenv('PRIVATE_KEY_PARAM')
PUBLIC_KEY_PARAM = os.getenv('PUBLIC_KEY_PARAM')
KID = os.getenv('KID')
REGION = os.getenv('REGION')
AUDIENCE = os.getenv('AUDIENCE')

ssm_client = boto3.client('ssm')

# Fetch private and public keys from SSM
def get_private_key():
    response = ssm_client.get_parameter(Name=PRIVATE_KEY_PARAM, WithDecryption=True)
    return response['Parameter']['Value']

def get_public_key():
    response = ssm_client.get_parameter(Name=PUBLIC_KEY_PARAM, WithDecryption=True)
    return response['Parameter']['Value']

def lambda_handler(event, context):    
    path = event['requestContext']['resourcePath']
    logger.info(f"Endpoint: {path}")
    logger.debug(json.dumps(event))

    if path == '/token':
        return handle_token(event)
    elif path == '/.well-known/openid-configuration':
        return handle_openid_configuration(event)
    elif path == '/.well-known/jwks.json':
        return handle_jwks(event)
    else:
        return {
            'statusCode': 404,
            'body': json.dumps({'error': 'Not Found'})
        }

def handle_token(event):
    try:                
        body = json.loads(event['body'])
        email = body.get('email')

        domain = event['requestContext']['domainName']
        stage = event['requestContext']['stage']
        issuer_url = f"https://{domain}/{stage}"

        if not email:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'email parameter is required'})
            }

        private_key = get_private_key()

        # Create token claims
        claims = {
            "sub": email,
            "aud": AUDIENCE,
            "iss": issuer_url,
            "iat": datetime.datetime.now(datetime.timezone.utc),
            "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1),
            "email": email,
            "https://aws.amazon.com/tags": {
                "principal_tags": {
                    "Email": [email]
                }
            }
        }

        # Encode JWT with RS256
        header = {
            "alg": "RS256",
            "kid": KID,
            "typ": "JWS"
        }

        token = jwt.encode(header=header, payload=claims, key=private_key)
        return {
            'isBase64Encoded': False,
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': '*',
                'Access-Control-Allow-Methods': '*',
                'Content-Type': 'application/json'
            },
            'body': json.dumps({'id_token': token.decode('utf-8')})
        }

    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }

def handle_openid_configuration(event):
    domain = event['requestContext']['domainName']
    stage = event['requestContext']['stage']
    issuer_url = f"https://{domain}/{stage}"

    openid_config = {
        "issuer": issuer_url,  # Dynamic issuer
        "jwks_uri": f"{issuer_url}/.well-known/jwks.json",  # JWKS URI
        "response_types_supported": ["id_token"],
        "subject_types_supported": ["public"],
        "id_token_signing_alg_values_supported": ["RS256"]
    }
    return {
        'isBase64Encoded': False,
        'statusCode': 200,
        'headers': {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': '*',
            'Access-Control-Allow-Methods': '*',
            'Content-Type': 'application/json'
        },
        'body': json.dumps(openid_config)
    }

def handle_jwks(event):
    public_key = get_public_key()
    
    # Convert public key to JWKS format
    jwk = JsonWebKey.import_key(public_key, {'kid': KID, 'alg': 'RS256', 'use': 'sig'})
    jwks = {
        "keys": [jwk.as_dict()]
    }
    return {
        'isBase64Encoded': False,
        'statusCode': 200,
        'headers': {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': '*',
            'Access-Control-Allow-Methods': '*',
            'Content-Type': 'application/json'
        },
        'body': json.dumps(jwks)
    }
