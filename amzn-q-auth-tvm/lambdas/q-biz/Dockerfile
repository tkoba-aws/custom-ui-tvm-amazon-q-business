FROM public.ecr.aws/lambda/python:3.10-x86_64

# Copy function code
COPY app.py ${LAMBDA_TASK_ROOT}/

# Install dependencies
RUN pip install --upgrade pip
COPY boto3-1.35.59-py3-none-any.whl .
COPY botocore-1.35.59-py3-none-any.whl .
RUN pip install ./botocore-1.35.59-py3-none-any.whl ./boto3-1.35.59-py3-none-any.whl --target "${LAMBDA_TASK_ROOT}"

# Set the CMD to your handler (app.lambda_handler)
CMD ["app.lambda_handler"]
