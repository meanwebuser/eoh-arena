FROM python:3.13-alpine
WORKDIR /app
COPY model ./model
COPY scripts ./scripts
COPY tests ./tests
CMD ["python", "-m", "unittest", "discover", "-s", "tests", "-v"]
