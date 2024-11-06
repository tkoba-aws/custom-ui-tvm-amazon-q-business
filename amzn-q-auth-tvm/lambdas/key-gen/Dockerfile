FROM public.ecr.aws/lambda/python:3.12-x86_64

# Copy function code
COPY app.py ${LAMBDA_TASK_ROOT}/

# Install dependencies
RUN pip install --upgrade pip
COPY requirements.txt .
RUN pip install -U -r requirements.txt --target "${LAMBDA_TASK_ROOT}"

# Set the CMD to your handler (app.lambda_handler)
CMD ["app.lambda_handler"]
