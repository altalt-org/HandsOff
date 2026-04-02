FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    android-tools-adb \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# droidrun-pkg를 먼저 설치 (로컬 패키지, build context 루트에서 복사)
COPY droidrun-pkg /droidrun-pkg
RUN pip install --no-cache-dir /droidrun-pkg

COPY server/requirements.txt .
RUN grep -v 'droidrun-pkg' requirements.txt | pip install --no-cache-dir -r /dev/stdin

COPY server/main.py .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
