FROM python:3.12-slim

WORKDIR /app

# Install runtime dependencies
COPY requirements.txt ./
RUN python -m pip install --upgrade pip \
    && python -m pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

ENV PYTHONUNBUFFERED=1
EXPOSE 5000

CMD ["python", "app.py"]
