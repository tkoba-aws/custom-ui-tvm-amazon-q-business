# Amazon Q Business Token Vending Maching (TVM) CDK Stack

First install the dependencies

```bash
cd amzn-q-auth-tvm
npm install --save
```

Create a `.env` file with following values

```
CDK_DEFAULT_ACCOUNT=<aws_account_id>
CDK_DEFAULT_REGION=<region>
```

Perform CDK synth

```bash
cdk synth
```

Deploy

```bash
cdk deploy
```