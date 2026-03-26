FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /opt/managerbot

COPY managerbot/pyproject.toml ./pyproject.toml
COPY managerbot/app ./app

RUN pip install --no-cache-dir .

EXPOSE 8080

CMD ["python", "-m", "app"]
