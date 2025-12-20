FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir fastapi==0.115.6 uvicorn==0.32.1
RUN pip install asyncpg

COPY main.py /app/main.py

EXPOSE 8080
CMD ["python", "-m", "uvicorn", "main:app", "--host=0.0.0.0", "--port=8080"]
