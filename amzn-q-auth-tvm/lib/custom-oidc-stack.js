const cdk = require('aws-cdk-lib');
const { Stack, Duration } = cdk;
const lambda = require('aws-cdk-lib/aws-lambda');
const apigateway = require('aws-cdk-lib/aws-apigateway');
const ssm = require('aws-cdk-lib/aws-ssm');
const iam = require('aws-cdk-lib/aws-iam');
const custom_resources = require('aws-cdk-lib/custom-resources');
const { randomBytes } = require('crypto');
const allowListedDomains = require("../allow-list-domains.json");

class MyOidcIssuerStack extends Stack {
  constructor(scope, id, props) {
    super(scope, id, props);

    const region = this.region;
    const accountId = this.account;
    const keyId = `${region}-kid`;

    // Generate a deterministic Audience for the OIDC issuer
    const audience = `${this.region}-${this.account}-tvm`;

    //Create allow-listed domains parameters in SSM
    new ssm.StringParameter(this, 'OIDCAllowListParameter', {
      parameterName: '/oidc/allow-list',
      stringValue: allowListedDomains.allowList.join(','),
      description: 'The Allow listed domains for TVM OIDC Provider'
    });

    // IAM Role for Key Generation Lambda
    const keyGenLambdaRole = new iam.Role(this, 'KeyGenLambdaRole', {
      roleName: 'KeyGenLambdaRole',
      assumedBy: new iam.ServicePrincipal('lambda.amazonaws.com'),
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName('service-role/AWSLambdaBasicExecutionRole')
      ]
    });

    keyGenLambdaRole.addToPolicy(new iam.PolicyStatement({
      effect: iam.Effect.ALLOW,
      actions: ['ssm:PutParameter', 'ssm:DeleteParameter', "ssm:DeleteParameters"],
      resources: [`arn:aws:ssm:${region}:${accountId}:parameter/oidc/private_key`,
                  `arn:aws:ssm:${region}:${accountId}:parameter/oidc/public_key`,
                  `arn:aws:ssm:${region}:${accountId}:parameter/oidc/client_id`,
                  `arn:aws:ssm:${region}:${accountId}:parameter/oidc/client_secret`]
    }));

    // IAM Role for OIDC Lambda
    const oidcLambdaRole = new iam.Role(this, 'OidcLambdaRole', {
      roleName: 'OidcLambdaRole',
      assumedBy: new iam.ServicePrincipal('lambda.amazonaws.com'),
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName('service-role/AWSLambdaBasicExecutionRole')
      ]
    });

    oidcLambdaRole.addToPolicy(new iam.PolicyStatement({
      effect: iam.Effect.ALLOW,
      actions: ['ssm:GetParameter'],
      resources: [
        `arn:aws:ssm:${region}:${accountId}:parameter/oidc/private_key`,
        `arn:aws:ssm:${region}:${accountId}:parameter/oidc/public_key`,
        `arn:aws:ssm:${region}:${accountId}:parameter/oidc/client_id`,
        `arn:aws:ssm:${region}:${accountId}:parameter/oidc/client_secret`,
        `arn:aws:ssm:${region}:${accountId}:parameter/oidc/allow-list`,
      ]
    }));

    // Lambda to generate RSA key pair and store in SSM
    const keyGenLambda = new lambda.DockerImageFunction(this, 'KeyGenLambda', {
      functionName: 'key-gen-lambda',
      code: lambda.DockerImageCode.fromImageAsset('lambdas/key-gen'),
      handler: 'app.lambda_handler',
      runtime: lambda.Runtime.PYTHON_3_11,
      timeout: Duration.seconds(300),
      role: keyGenLambdaRole
    });

    const keyGenProvider = new custom_resources.Provider(this, 'KeyGenProvider', {
      onEventHandler: keyGenLambda,
    });

    new cdk.CustomResource(this, 'KeyGenCustomResource', {
      serviceToken: keyGenProvider.serviceToken,
    });

    // Lambda Authorizer function for API Gateway
    const authorizerLambda = new lambda.Function(this, 'OIDCLambdaAuthorizerFn', {
      functionName: 'oidc-lambda-authorizer',
      code: lambda.Code.fromAsset('lambdas/lambda-authorizer'),
      handler: 'app.lambda_handler',
      environment: {        
        CLIENT_ID_PARAM: '/oidc/client_id',
        CLIENT_SECRET_PARAM: '/oidc/client_secret',
        OIDC_ALLOW_LIST: '/oidc/allow-list'
      },
      runtime: lambda.Runtime.PYTHON_3_11,
      timeout: Duration.seconds(300),
      role: oidcLambdaRole
    });

    // Create the API Gateway (API URL not needed here)
    const api = new apigateway.RestApi(this, 'OidcApi', {
        restApiName: 'OIDC Issuer Service',
        description: 'Handles OIDC issuance and verification.',
        defaultCorsPreflightOptions: {
          allowOrigins: apigateway.Cors.ALL_ORIGINS,
          allowMethods: apigateway.Cors.ALL_METHODS,
          allowHeaders: apigateway.Cors.DEFAULT_HEADERS,
          exposeHeaders: ['Access-Control-Allow-Origin',
                          'Access-Control-Allow-Credentials',],
          statusCode: 200,
          allowCredentials: false
        },
        deployOptions:{
            loggingLevel: apigateway.MethodLoggingLevel.INFO,
            dataTraceEnabled: true,            
        },
        cloudWatchRole: true,      
    });

    const oidcLambda = new lambda.DockerImageFunction(this, 'OidcLambda', {
      functionName: 'oidc-lambda',
      code: lambda.DockerImageCode.fromImageAsset('lambdas/oidc-issuer'),
      environment: {
        PRIVATE_KEY_PARAM: '/oidc/private_key',
        PUBLIC_KEY_PARAM: '/oidc/public_key',
        KID: keyId,
        REGION: region,
        AUDIENCE: audience,
      },
      runtime: lambda.Runtime.PYTHON_3_11,
      timeout: Duration.seconds(300),
      role: oidcLambdaRole
    });

    // Set up API Gateway routes (without issuer URL yet)
    // Create the Lambda Authorizer
    const authorizer = new apigateway.RequestAuthorizer(this, 'OIDCLambdaAuthorizer', {
      handler: authorizerLambda,
      identitySources: [apigateway.IdentitySource.header('Authorization')],
    });

    const tokenResource = api.root.addResource('token');
    tokenResource.addMethod('POST', new apigateway.LambdaIntegration(oidcLambda), {
        authorizer,
        authorizationType: apigateway.AuthorizationType.CUSTOM
    });

    const wellknown = api.root.addResource('.well-known');
    const openidResource = wellknown.addResource('openid-configuration');
    openidResource.addMethod('GET', new apigateway.LambdaIntegration(oidcLambda));

    const jwksResource = wellknown.addResource('jwks.json');
    jwksResource.addMethod('GET', new apigateway.LambdaIntegration(oidcLambda));

    // Define the IAM role for the Custom Resource Lambda (update-lambda)
    const updateLambdaRole = new iam.Role(this, 'UpdateLambdaRole', {
      roleName: 'update-oidc-lambda-role',
      assumedBy: new iam.ServicePrincipal('lambda.amazonaws.com'),  // The Lambda service
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName('service-role/AWSLambdaBasicExecutionRole'),  // CloudWatch logs
      ],
    });

    // Grant permission to update the OIDC Lambda function environment variables
    updateLambdaRole.addToPolicy(new iam.PolicyStatement({
      effect: iam.Effect.ALLOW,
      actions: [
        'lambda:GetFunctionConfiguration',
        'lambda:UpdateFunctionConfiguration'
      ],
      resources: [oidcLambda.functionArn]  // The OIDC Lambda's ARN
    }));

    // Grant permissions to create and manage IAM Identity Providers
    updateLambdaRole.addToPolicy(new iam.PolicyStatement({
      effect: iam.Effect.ALLOW,
      actions: [
        'iam:CreateOpenIDConnectProvider',
        'iam:DeleteOpenIDConnectProvider',
        'iam:GetOpenIDConnectProvider'
      ],
      resources: [`arn:aws:iam::${accountId}:oidc-provider/*`]
    }));

    // Grant permissions to create and manage IAM Roles
    updateLambdaRole.addToPolicy(new iam.PolicyStatement({
      effect: iam.Effect.ALLOW,
      actions: [
        'iam:CreateRole',
        'iam:DeleteRole',
        'iam:GetRole',
        'iam:PutRolePolicy',
        'iam:AttachRolePolicy'
      ],
      resources: [`arn:aws:iam::${accountId}:role/*`]  // Allow creating and managing IAM roles in this account
    }));

    const updateLambda = new lambda.Function(this, 'UpdateLambdaEnv', {
      functionName: 'oidc-lambda-updater',
      code: lambda.Code.fromAsset('lambdas/update-lambda'),  // Path to your update Lambda code
      handler: 'app.lambda_handler',
      runtime: lambda.Runtime.PYTHON_3_11,
      environment: {
        FUNCTION_NAME: oidcLambda.functionName,  // Pass the OIDC Lambda function name
        API_URL: api.url,  // Pass the API Gateway URL
        AUDIENCE: audience  // Pass the audience
      },
      timeout: Duration.seconds(300),
      role: updateLambdaRole,  // Ensure this Lambda has permission to update the function
    });
    
    const updateLambdaProvider = new custom_resources.Provider(this, 'UpdateLambdaProvider', {
      onEventHandler: updateLambda,
    });
    
    new cdk.CustomResource(this, 'UpdateLambdaCustomResource', {
      serviceToken: updateLambdaProvider.serviceToken,
    });

    // Output Audience Id
    new cdk.CfnOutput(this, 'AudienceOutput', {
      description: 'OIDC Audience ID',
      value: audience,
      exportName: 'OIDCAudience',
    });

    // Output API URL
    new cdk.CfnOutput(this, 'IssuerUrlOutput', {
      description: 'Issuer URL (API Gateway)',
      value: api.url,
      exportName: 'IssuerUrl',
    });

    //Output Q Business Role to Assume q-biz-custom-oidc-assume-role
    new cdk.CfnOutput(this, 'QBizAssumeRoleARN', {
      description: 'Amazon Q Business Role to Assume',
      value: `arn:aws:iam::${accountId}:role/q-biz-custom-oidc-assume-role`,
      exportName: 'AssumeRoleARN',
    });
  }
}

module.exports = { MyOidcIssuerStack };
