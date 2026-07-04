FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY economics_daily ./economics_daily
COPY prompts ./prompts

ENTRYPOINT ["python", "-m", "economics_daily"]
