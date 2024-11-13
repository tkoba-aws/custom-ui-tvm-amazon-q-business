#!/usr/bin/env node
require('dotenv').config()
const cdk = require('aws-cdk-lib');
const { TVMOidcIssuerStack } = require('../lib/custom-oidc-stack');
const { AwsSolutionsChecks, NagSuppressions } = require('cdk-nag')

const app = new cdk.App();
const stack = new TVMOidcIssuerStack(app, 'TVMOidcIssuerStack', {
  env: { 
    account: process.env.CDK_DEFAULT_ACCOUNT, 
    region: process.env.CDK_DEFAULT_REGION 
  },
});

cdk.Aspects.of(app).add(new AwsSolutionsChecks({ verbose: true }));

/**
 * Add nag suppressions for known architectural decisions
 */
NagSuppressions.addStackSuppressions(stack, [
  { id: 'AwsSolutions-COG4', reason: 'API Gateway uses custom Lambda Authorizer for /token endpoint' },
  { id: 'AwsSolutions-APIG4', reason: 'API Gateway uses custom Lambda Authorizer for /token endpoint' },
  { id: 'AwsSolutions-APIG3', reason: 'Customer to decide if WAF is required since there are costs associated' },
  { id: 'AwsSolutions-APIG1', reason: 'API Gateway default logging is enabled via deployOptions' },
  { id: 'AwsSolutions-IAM4', reason: 'AWSLambdaBasicExecutionRole is scoped in`' },
  { id: 'AwsSolutions-IAM5', reason: 'CreateOpenIDConnectProvider requires oidc-provider/*' },
  { id: 'AwsSolutions-L1', reason: 'Python 3.11 to stay compatible for Authlib' },
  { id: 'AwsSolutions-APIG2', reason: 'REST API request validation is handled by Lambda Flask' },
]);


