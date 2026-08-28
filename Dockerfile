FROM node:22-slim AS web-build
WORKDIR /app/web
COPY web/package*.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    EC_DATA_DIR=/data \
    PORT=8080
WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 libglib2.0-0 libgl1 fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
COPY requirements-cloud.txt ./
RUN pip install --no-cache-dir -r requirements-cloud.txt
COPY . ./
COPY --from=web-build /app/web/dist ./web/dist
RUN mkdir -p /data
EXPOSE 8080
CMD ["python", "cloud_runner.py"]
