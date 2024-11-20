# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import json
import boto3
import os
import uuid
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend

import logging

log_level = os.environ.get('LOG_LEVEL', 'DEBUG')
logger = logging.getLogger(__name__)
logger.setLevel(log_level)

ssm_client = boto3.client('ssm')
sts = boto3.client('sts')

def lambda_handler(event, context):
    logger.debug(json.dumps(event))

    request_type = event['RequestType']

    if request_type == "Create":   
        try:
            logger.info("Generating private key...")
            # Generate RSA Private Key
            private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=2048,
                backend=default_backend()
            )

            # Serialize private key
            logger.info("Encrypting private key...")
            private_pem = private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption()
            )

            # Serialize public key
            logger.info("Generating public key for private key...")
            public_key = private_key.public_key()
            public_pem = public_key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            )

            # Store the private key in SSM Parameter Store (encrypted)
            logger.info("Storing encrypted private key into SSM Parameter store...")
            ssm_client.put_parameter(
                Name='/oidc/private_key',
                Value=private_pem.decode('utf-8'),
                Type='SecureString',
                Overwrite=True
            )

            # Store the public key in SSM Parameter Store (encrypted)
            logger.info("Storing public key into SSM Parameter store...")
            ssm_client.put_parameter(
                Name='/oidc/public_key',
                Value=public_pem.decode('utf-8'),
                Type='SecureString',
                Overwrite=True
            )
            
            # account_id = sts.get_caller_identity()['Account']
            # client_id = f"oidc-tvm-{account_id}"
            # client_secret = uuid.uuid4().hex
            # # Store the client id in SSM Parameter Store (encrypted)
            # logger.info("Storing client ID into SSM Parameter store...")
            # ssm_client.put_parameter(
            #     Name='/oidc/client_id',
            #     Value=client_id,
            #     Type='String',
            #     Overwrite=True
            # )

            # # Store the client secret in SSM Parameter Store (encrypted)
            # logger.info("Storing client secret into SSM Parameter store...")
            # ssm_client.put_parameter(
            #     Name='/oidc/client_secret',
            #     Value=client_secret,
            #     Type='SecureString',
            #     Overwrite=True
            # )

            logger.info('RSA key pair successfully generated and stored in SSM.')
            return {
                'statusCode': 200,
                'body': json.dumps('RSA key pair successfully generated and stored in SSM.')
            }

        except Exception as e:
            return {
                'statusCode': 500,
                'body': json.dumps(f'Error generating or storing key: {str(e)}')
            }
    
    if request_type == "Delete":
        try:            
            ssm_client.delete_parameters(
                    Names=[
                        '/oidc/public_key',
                        '/oidc/private_key',
                        '/oidc/client_id',
                        '/oidc/client_secret'
                    ]
                )
            logger.info('RSA key pair, client ID, and secret successfully deleted from SSM.')
        except Exception as e:
            return {
                'statusCode': 500,
                'body': json.dumps(f'Error deleting key in parameter store: {str(e)}')
            }