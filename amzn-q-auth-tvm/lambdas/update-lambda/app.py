# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import boto3
import os
import json
import time
import logging

log_level = os.environ.get('LOG_LEVEL', 'DEBUG')
logger = logging.getLogger(__name__)
logger.setLevel(log_level)

lambda_client = boto3.client('lambda')
iam_client = boto3.client('iam')

def lambda_handler(event, context):
    # Get the Lambda function name and API Gateway URL from environment variables
    logger.debug(json.dumps(event))

    request_type = event['RequestType']

    function_name = os.environ['FUNCTION_NAME']
    api_url = os.environ['API_URL'].rstrip('/')
    audience = os.environ['AUDIENCE']
    account_id = context.invoked_function_arn.split(":")[4]

    if request_type == "Create":        
        try:
            # Get the existing environment variables from the target Lambda function
            response = lambda_client.get_function_configuration(FunctionName=function_name)
            existing_env_vars = response['Environment']['Variables']

            # Update environment variables with new ones
            updated_env_vars = existing_env_vars.copy()  # Copy existing variables
            updated_env_vars['ISSUER_URL'] = api_url  # Add API URL
            updated_env_vars['AUDIENCE'] = audience  # Add audience

            # Update the Lambda function with new environment variables
            lambda_client.update_function_configuration(
                FunctionName=function_name,
                Environment={'Variables': updated_env_vars}
            )

            # Step 1: Create IAM Identity Provider
            time.sleep(15) #wait for API Gateway to become available
            identity_provider_arn = create_iam_identity_provider(api_url, account_id)

            # Step 2: Create IAM Role and Trust Policy
            create_iam_role(identity_provider_arn, audience, account_id)

            return {
                'statusCode': 200,
                'body': 'Lambda environment variables updated and IAM Identity provider created successfully.'
            }
        except Exception as e:
            print(f"Error updating Lambda environment variables: {str(e)}")
            return {
                'statusCode': 500,
                'body': f"Error: {str(e)}"
            }
    
    if request_type == "Delete":
        try:
            api_url=api_url.replace('https://','')            
            iam_client.delete_open_id_connect_provider(OpenIDConnectProviderArn=f"arn:aws:iam::{account_id}:oidc-provider/{api_url}")
            iam_client.delete_role_policy(
                        RoleName='q-biz-custom-oidc-policy',
                        PolicyName='q-biz-custom-oidc-assume-role'
                    )
            iam_client.delete_role(RoleName='q-biz-custom-oidc-assume-role')
        except Exception as e:
            print(str(e))
            raise Exception(str(e))

def create_iam_identity_provider(issuer_url, account_id):
    try:
        response = iam_client.create_open_id_connect_provider(
            Url=issuer_url,            
            ClientIDList=[os.environ['AUDIENCE']]
        )
        provider_arn = response['OpenIDConnectProviderArn']
        print(f"IAM Identity Provider created: {provider_arn}")
        return provider_arn
    except iam_client.exceptions.EntityAlreadyExistsException:
        provider_arn = f"arn:aws:iam::{account_id}:oidc-provider/{issuer_url}"
        print(f"IAM Identity Provider already exists: {provider_arn}")
        return provider_arn
    except Exception as e:
        raise Exception(f"Failed to create IAM Identity Provider: {str(e)}")

def create_iam_role(provider_arn, audience, account_id):
    role_name = 'q-biz-custom-oidc-assume-role'
    
    try:
        # Define the trust policy
        iss_url = os.environ['API_URL'].replace('https://','').rstrip('/')
        region = os.environ['AWS_REGION']
        trust_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {
                        "Federated": provider_arn
                    },
                    "Action": "sts:AssumeRoleWithWebIdentity",
                    "Condition": {
                        "StringEquals": {
                            f"{iss_url}:aud": audience
                        },
                        "StringLike": {
                            "aws:RequestTag/Email": "*"
                        }
                    }
                },
                {
                    "Effect": "Allow",
                    "Principal": {
                        "Federated": provider_arn
                    },
                    "Action": "sts:TagSession",
                    "Condition": {
                        "StringLike": {
                            "aws:RequestTag/Email": "*"
                        }
                    }
                },
                {
                    "Sid": "QBusinessTrustPolicy",
                    "Effect": "Allow",
                    "Principal": {
                        "Service": "application.qbusiness.amazonaws.com"
                    },
                    "Action": [
                        "sts:AssumeRole",
                        "sts:SetContext"
                    ],
                    "Condition": {
                        "StringEquals": {
                            "aws:SourceAccount": account_id
                        },
                        "ArnEquals": {
                            "aws:SourceArn": f"arn:aws:qbusiness:{region}:{account_id}:application/*"
                        }
                    }
                }
                
            ]
        }

        # Create the IAM Role
        response = iam_client.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=json.dumps(trust_policy),
            Description="Role for OIDC-based authentication in q-business."
        )
        print(f"IAM Role created: {response['Role']['Arn']}")

        # Attach permissions to the role
        attach_permissions_to_role(role_name, account_id)

    except iam_client.exceptions.EntityAlreadyExistsException:
        print(f"IAM Role {role_name} already exists.")
    except Exception as e:
        raise Exception(f"Failed to create IAM Role: {str(e)}")

def attach_permissions_to_role(role_name, account_id):
    try:
        # Define the permissions policy
        permissions_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "QBusinessConversationPermission",
                    "Effect": "Allow",
                    "Action": [
                        "qbusiness:Chat",
                        "qbusiness:ChatSync",
                        "qbusiness:Retrieve",                
                        "qbusiness:ListMessages",
                        "qbusiness:ListConversations",                
                        "qbusiness:PutFeedback",
                        "qbusiness:DeleteConversation"
                    ],
                    "Resource": f"arn:aws:qbusiness:us-east-1:{account_id}:application/*"
                },
                {
                    "Sid": "QBusinessSetContextPermissions",
                    "Effect": "Allow",
                    "Action": [
                        "sts:SetContext"
                    ],
                    "Resource": [
                        "arn:aws:sts::*:self"
                    ],
                    "Condition": {
                        "StringLike": {
                            "aws:CalledViaLast": [
                                "qbusiness.amazonaws.com"
                            ]
                        }
                    }
                },
                {
                    "Effect": "Allow",
                    "Action": "user-subscriptions:CreateClaim",
                    "Resource": "*"
                }
            ]
        }

        # Attach the permissions policy to the role
        iam_client.put_role_policy(
            RoleName=role_name,
            PolicyName='q-biz-custom-oidc-policy',
            PolicyDocument=json.dumps(permissions_policy)
        )
        print(f"Permissions attached to IAM Role: {role_name}")

    except Exception as e:
        raise Exception(f"Failed to attach permissions to IAM Role: {str(e)}")