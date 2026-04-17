FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[dev]"

COPY . .
RUN pip install --no-cache-dir -e ".[dev]"

CMD ["pytest"]
