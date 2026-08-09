FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN mkdir -p /data /app/output/previews /app/output/charts
ENV DATABASE_PATH=/data/coincoach.db
CMD ["python", "-m", "app.main", "api", "--host", "0.0.0.0", "--port", "8080"]
